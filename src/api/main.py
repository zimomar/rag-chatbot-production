"""
API REST pour le chatbot RAG Local.
"""

import json
import logging
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from src.agent.graph import RAGAgent, RAGResponse, Source
from src.config import settings
from src.ingestion.loader import DocumentLoader
from src.ingestion.chunker import Chunker
from src.ingestion.embedder import Embedder
from src.retrieval.store import VectorStore

# Configuration du logging
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RAG Local API",
    description="API pour un chatbot RAG 100% local",
    version="0.2.0",
)


# ---------------------------------------------------------------------------
# API Key Authentication Middleware (optionnel)
# ---------------------------------------------------------------------------
class APIKeyMiddleware(BaseHTTPMiddleware):
    """Vérifie la clé API si APP_API_KEY est configurée."""

    async def dispatch(self, request: Request, call_next):
        if not settings.app_api_key:
            return await call_next(request)

        # Endpoints publics (health check, docs)
        public_paths = {"/health", "/docs", "/openapi.json", "/redoc"}
        if request.url.path in public_paths:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        if api_key != settings.app_api_key:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={"detail": "Clé API invalide ou manquante. Ajoutez le header X-API-Key."},
            )
        return await call_next(request)


app.add_middleware(APIKeyMiddleware)

# Initialisation des composants
loader = DocumentLoader()
chunker = Chunker()
embedder = Embedder()
vector_store = VectorStore()
agent = RAGAgent(vector_store=vector_store, embedder=embedder)

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class MessageModel(BaseModel):
    """Message dans l'historique de conversation."""
    role: str
    content: str


class QueryRequest(BaseModel):
    """Requête de question avec historique optionnel (multi-turn)."""
    question: str
    history: Optional[List[MessageModel]] = None


class SourceModel(BaseModel):
    """Modèle de source pour l'API."""
    document: str
    page: Optional[int]
    excerpt: str
    relevance_score: float


class QueryResponse(BaseModel):
    """Réponse de question."""
    answer: str
    sources: List[SourceModel]
    confidence: float


class FeedbackRequest(BaseModel):
    """Feedback utilisateur sur une réponse."""
    question: str
    answer: str
    rating: int  # 1 = positive, 0 = negative
    comment: Optional[str] = None


class ComplianceReportRequest(BaseModel):
    """Requête pour un rapport de conformité."""
    regulations: List[str] = ["NIS2", "DORA", "RGPD", "AI Act"]
    custom_questions: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Feedback storage (fichier JSON simple)
# ---------------------------------------------------------------------------
FEEDBACK_FILE = settings.upload_dir.parent / "feedback.json"


def _save_feedback(entry: dict) -> None:
    """Ajoute un feedback au fichier JSON."""
    import json as json_lib
    from datetime import datetime, timezone
    entries = []
    if FEEDBACK_FILE.exists():
        try:
            entries = json_lib.loads(FEEDBACK_FILE.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    entries.append(entry)
    FEEDBACK_FILE.write_text(json_lib.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    """Vérifie la configuration au démarrage."""
    logger.info("Vérification de la connexion aux services...")
    
    if not embedder.check_connection():
        logger.error(f"CRITIQUE : Impossible de contacter Ollama sur {settings.ollama_host}")
    else:
        if not embedder.check_model_available():
            logger.warning(
                f"ATTENTION : Le modèle d'embedding '{settings.ollama_embed_model}' n'est pas installé sur Ollama. "
                f"Lancez : docker exec -it rag-ollama ollama pull {settings.ollama_embed_model}"
            )

    if not vector_store.check_connection():
        logger.error(f"CRITIQUE : Impossible de contacter ChromaDB sur {settings.chroma_url}")


# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check():
    """Vérifie la santé de l'API et des services."""
    return {
        "status": "healthy",
        "ollama": embedder.check_connection(),
        "chromadb": vector_store.check_connection(),
    }


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload et indexation d'un document (PDF, MD, DOCX, PPTX)."""
    if file.size > settings.max_file_size_bytes:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux")

    try:
        content = await file.read()
        doc = loader.load_uploaded_file(content, file.filename)
        chunks = chunker.split(doc)
        embedded_chunks = embedder.embed_chunks(chunks)
        vector_store.add_documents(embedded_chunks)
        
        return {"status": "success", "chunks": len(chunks), "source": file.filename}
    except Exception as e:
        logger.error(f"Erreur d'indexation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query", response_model=QueryResponse)
async def query_agent(request: QueryRequest):
    """Pose une question au chatbot RAG (avec historique multi-turn optionnel)."""
    try:
        history = [{"role": m.role, "content": m.content} for m in request.history] if request.history else None
        response: RAGResponse = await agent.answer(request.question, history=history)
        
        api_sources = [
            SourceModel(
                document=s.document,
                page=s.page,
                excerpt=s.excerpt,
                relevance_score=s.relevance_score
            ) for s in response.sources
        ]
        
        return QueryResponse(
            answer=response.answer,
            sources=api_sources,
            confidence=response.confidence
        )
    except Exception as e:
        logger.error(f"Erreur agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Streaming endpoint (SSE)
# ---------------------------------------------------------------------------
@app.post("/query/stream")
async def query_stream(request: QueryRequest):
    """Streaming SSE : retourne la réponse token par token."""

    async def event_generator():
        history = [{"role": m.role, "content": m.content} for m in request.history] if request.history else None
        async for chunk in agent.stream_answer(request.question, history=history):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Feedback endpoint
# ---------------------------------------------------------------------------
@app.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    """Enregistre le feedback utilisateur (👍/👎) sur une réponse."""
    try:
        _save_feedback({
            "question": request.question,
            "answer": request.answer[:500],
            "rating": request.rating,
            "comment": request.comment,
        })
        return {"status": "saved"}
    except Exception as e:
        logger.error(f"Erreur feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/feedback")
def list_feedback():
    """Liste tous les feedbacks enregistrés."""
    import json as json_lib
    if not FEEDBACK_FILE.exists():
        return {"feedback": [], "total": 0}
    try:
        entries = json_lib.loads(FEEDBACK_FILE.read_text(encoding="utf-8"))
        positive = sum(1 for e in entries if e.get("rating") == 1)
        return {"feedback": entries, "total": len(entries), "positive": positive, "negative": len(entries) - positive}
    except Exception:
        return {"feedback": [], "total": 0}


# ---------------------------------------------------------------------------
# Compliance Report endpoint
# ---------------------------------------------------------------------------
@app.post("/compliance-report")
async def generate_compliance_report(request: ComplianceReportRequest):
    """Génère un rapport de conformité automatique basé sur les documents indexés."""
    # Questions-types par réglementation
    regulation_questions = {
        "NIS2": [
            "Quelles sont les obligations de la directive NIS2 pour les entités essentielles ?",
            "Quels sont les délais de notification d'incident selon NIS2 ?",
            "Quelles mesures de cybersécurité sont exigées par NIS2 ?",
        ],
        "DORA": [
            "Quelles sont les exigences de DORA en matière de résilience opérationnelle numérique ?",
            "Comment DORA encadre-t-il les prestataires tiers de services TIC ?",
            "Quels sont les tests de résilience requis par DORA ?",
        ],
        "RGPD": [
            "Quelles sont les bases légales de traitement des données personnelles selon le RGPD ?",
            "Quels sont les droits des personnes concernées sous le RGPD ?",
            "Quelles sont les obligations du responsable de traitement ?",
        ],
        "AI Act": [
            "Comment le AI Act classifie-t-il les systèmes d'IA par niveau de risque ?",
            "Quelles obligations s'appliquent aux systèmes d'IA à haut risque ?",
            "Quelles pratiques d'IA sont interdites par le AI Act ?",
        ],
    }

    sections = []
    for regulation in request.regulations:
        questions = regulation_questions.get(regulation, [])
        if request.custom_questions:
            questions.extend(request.custom_questions)

        answers = []
        for question in questions:
            try:
                response: RAGResponse = await agent.answer(question)
                answers.append({
                    "question": question,
                    "answer": response.answer,
                    "confidence": response.confidence,
                    "sources": [
                        {"document": s.document, "page": s.page, "excerpt": s.excerpt[:150]}
                        for s in response.sources
                    ],
                })
            except Exception as e:
                logger.error(f"Erreur rapport conformité ({regulation}): {e}")
                answers.append({
                    "question": question,
                    "answer": "Erreur lors de l'analyse.",
                    "confidence": 0.0,
                    "sources": [],
                })

        sections.append({
            "regulation": regulation,
            "answers": answers,
        })

    return {"report": sections, "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# Document management
# ---------------------------------------------------------------------------
@app.get("/documents")
def list_documents():
    """Liste les documents indexés."""
    return {"documents": vector_store.list_sources()}


@app.delete("/documents/{filename}")
def delete_document(filename: str):
    """Supprime un document de la base."""
    count = vector_store.delete_by_source(filename)
    return {"status": "deleted", "chunks": count}


class InfraAnalysisResponse(BaseModel):
    """Réponse d'analyse d'infrastructure."""
    description: str
    analysis: str
    sources: List[SourceModel]
    confidence: float


@app.post("/analyze-infrastructure", response_model=InfraAnalysisResponse)
async def analyze_infrastructure(
    file: UploadFile = File(...),
    question: str = Form(default=""),
):
    """
    Analyse un diagramme d'infrastructure vis-à-vis des réglementations européennes.
    Accepte une image (PNG, JPG, PDF) et une question optionnelle.
    """
    try:
        content = await file.read()

        # 1. Description de l'image via le modèle vision
        description = agent.describe_image(content)
        if not description:
            raise HTTPException(
                status_code=422,
                detail="Impossible de décrire l'image. Vérifiez que le modèle vision est installé."
            )

        # 2. Construction de la requête d'analyse
        eu_prompt = (
            f"Voici une description de l'infrastructure IT d'une entreprise :\n\n"
            f"{description}\n\n"
            f"En te basant sur les documents indexés concernant les réglementations européennes "
            f"(NIS2, DORA, AI Act, GDPR, Cyber Resilience Act, etc.), analyse cette infrastructure et identifie :\n"
            f"1. Les composants qui sont concernés par des obligations réglementaires\n"
            f"2. Les risques de non-conformité\n"
            f"3. Les actions prioritaires à entreprendre\n"
            f"4. Les échéances réglementaires pertinentes\n"
        )

        if question:
            eu_prompt += f"\nQuestion spécifique de l'utilisateur : {question}\n"

        # 3. Analyse RAG
        response: RAGResponse = await agent.answer(eu_prompt)

        api_sources = [
            SourceModel(
                document=s.document,
                page=s.page,
                excerpt=s.excerpt,
                relevance_score=s.relevance_score
            ) for s in response.sources
        ]

        return InfraAnalysisResponse(
            description=description,
            analysis=response.answer,
            sources=api_sources,
            confidence=response.confidence,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur analyse infrastructure: {e}")
        raise HTTPException(status_code=500, detail=str(e))

