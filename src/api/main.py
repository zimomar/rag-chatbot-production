"""
API REST pour le chatbot RAG Local.
"""

import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from src.agent.graph import RAGAgent, RAGResponse
from src.config import settings
from src.ingestion.chunker import Chunker
from src.ingestion.embedder import Embedder
from src.ingestion.loader import DocumentLoader
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

    async def dispatch(  # type: ignore[override]
        self, request: Request, call_next: Any
    ) -> Any:
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
    history: list[MessageModel] | None = None


class SourceModel(BaseModel):
    """Modèle de source pour l'API."""

    document: str
    page: int | None
    excerpt: str
    relevance_score: float


class QueryResponse(BaseModel):
    """Réponse de question."""

    answer: str
    sources: list[SourceModel]
    confidence: float


class FeedbackRequest(BaseModel):
    """Feedback utilisateur sur une réponse."""

    question: str
    answer: str
    rating: int  # 1 = positive, 0 = negative
    comment: str | None = None


class ComplianceReportRequest(BaseModel):
    """Requête pour un rapport de conformité."""

    regulations: list[str] = ["NIS2", "DORA", "RGPD", "AI Act"]
    custom_questions: list[str] | None = None


# ---------------------------------------------------------------------------
# Feedback storage (fichier JSON simple)
# ---------------------------------------------------------------------------
FEEDBACK_FILE = settings.upload_dir.parent / "feedback.json"


def _save_feedback(entry: dict[str, object]) -> None:
    """Ajoute un feedback au fichier JSON."""
    import json as json_lib
    from datetime import datetime

    entries = []
    if FEEDBACK_FILE.exists():
        try:
            entries = json_lib.loads(FEEDBACK_FILE.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    entry["timestamp"] = datetime.now(UTC).isoformat()
    entries.append(entry)
    FEEDBACK_FILE.write_text(
        json_lib.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event() -> None:
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
def health_check() -> dict[str, Any]:
    """Vérifie la santé de l'API et des services."""
    return {
        "status": "healthy",
        "ollama": embedder.check_connection(),
        "chromadb": vector_store.check_connection(),
    }


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload et indexation d'un document (PDF, MD, DOCX, PPTX)."""
    file_size = file.size or 0
    if file_size > settings.max_file_size_bytes:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux")

    filename = file.filename or "upload"
    try:
        content = await file.read()
        doc = loader.load_uploaded_file(content, filename)
        chunks = chunker.split(doc)
        embedded_chunks = embedder.embed_chunks(chunks)
        vector_store.add_documents(embedded_chunks)

        return {"status": "success", "chunks": len(chunks), "source": filename}
    except Exception as e:
        logger.error(f"Erreur d'indexation: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/query", response_model=QueryResponse)
async def query_agent(request: QueryRequest) -> QueryResponse:
    """Pose une question au chatbot RAG (avec historique multi-turn optionnel)."""
    try:
        history = (
            [{"role": m.role, "content": m.content} for m in request.history]
            if request.history
            else None
        )
        response: RAGResponse = await agent.answer(request.question, history=history)

        api_sources = [
            SourceModel(
                document=s.document,
                page=s.page,
                excerpt=s.excerpt,
                relevance_score=s.relevance_score,
            )
            for s in response.sources
        ]

        return QueryResponse(
            answer=response.answer, sources=api_sources, confidence=response.confidence
        )
    except Exception as e:
        logger.error(f"Erreur agent: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Streaming endpoint (SSE)
# ---------------------------------------------------------------------------
@app.post("/query/stream")
async def query_stream(request: QueryRequest) -> StreamingResponse:
    """Streaming SSE : retourne la réponse token par token."""

    async def event_generator() -> AsyncGenerator[str, None]:
        history = (
            [{"role": m.role, "content": m.content} for m in request.history]
            if request.history
            else None
        )
        async for chunk in agent.stream_answer(request.question, history=history):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Feedback endpoint
# ---------------------------------------------------------------------------
@app.post("/feedback")
async def submit_feedback(request: FeedbackRequest) -> dict[str, Any]:
    """Enregistre le feedback utilisateur (👍/👎) sur une réponse."""
    try:
        _save_feedback(
            {
                "question": request.question,
                "answer": request.answer[:500],
                "rating": request.rating,
                "comment": request.comment,
            }
        )
        return {"status": "saved"}
    except Exception as e:
        logger.error(f"Erreur feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/feedback")
def list_feedback() -> dict[str, Any]:
    """Liste tous les feedbacks enregistrés."""
    import json as json_lib

    if not FEEDBACK_FILE.exists():
        return {"feedback": [], "total": 0}
    try:
        entries = json_lib.loads(FEEDBACK_FILE.read_text(encoding="utf-8"))
        positive = sum(1 for e in entries if e.get("rating") == 1)
        return {
            "feedback": entries,
            "total": len(entries),
            "positive": positive,
            "negative": len(entries) - positive,
        }
    except Exception:
        return {"feedback": [], "total": 0}


# ---------------------------------------------------------------------------
# Compliance Report endpoint
# ---------------------------------------------------------------------------
@app.post("/compliance-report")
async def generate_compliance_report(request: ComplianceReportRequest) -> dict[str, Any]:
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
                answers.append(
                    {
                        "question": question,
                        "answer": response.answer,
                        "confidence": response.confidence,
                        "sources": [
                            {"document": s.document, "page": s.page, "excerpt": s.excerpt[:150]}
                            for s in response.sources
                        ],
                    }
                )
            except Exception as e:
                logger.error(f"Erreur rapport conformité ({regulation}): {e}")
                answers.append(
                    {
                        "question": question,
                        "answer": "Erreur lors de l'analyse.",
                        "confidence": 0.0,
                        "sources": [],
                    }
                )

        sections.append(
            {
                "regulation": regulation,
                "answers": answers,
            }
        )

    from datetime import datetime

    return {"report": sections, "generated_at": datetime.now(UTC).isoformat()}


# ---------------------------------------------------------------------------
# Document management
# ---------------------------------------------------------------------------
@app.get("/documents")
def list_documents() -> dict[str, Any]:
    """Liste les documents indexés."""
    return {"documents": vector_store.list_sources()}


@app.delete("/documents/{filename}")
def delete_document(filename: str) -> dict[str, Any]:
    """Supprime un document de la base."""
    count = vector_store.delete_by_source(filename)
    return {"status": "deleted", "chunks": count}


class InfraAnalysisResponse(BaseModel):
    """Réponse d'analyse d'infrastructure."""

    description: str
    analysis: str
    sources: list[SourceModel]
    confidence: float


@app.post("/analyze-infrastructure", response_model=InfraAnalysisResponse)
async def analyze_infrastructure(
    file: UploadFile = File(...),
    question: str = Form(default=""),
) -> InfraAnalysisResponse:
    """
    Analyse un diagramme d'infrastructure vis-à-vis des réglementations européennes.
    Accepte une image (PNG, JPG, PDF) et une question optionnelle.
    """
    try:
        content = await file.read()

        # 1. Obtenir la description de l'infrastructure
        filename = (file.filename or "").lower()

        if filename.endswith((".docx", ".pdf")):
            # Extract text automatically (NO truncation - will use RAG extraction)
            doc = loader.load_uploaded_file(content, filename)
            description = doc.content
            logger.info(f"Extracted DAT document: {len(description)} chars")
        else:
            # Vision model fallback for actual images
            description = agent.describe_image(content)
            if not description:
                raise HTTPException(
                    status_code=422,
                    detail="Impossible de décrire l'image. Vérifiez que le modèle vision est installé.",
                )

        # 2. Construction de la requête d'analyse
        # 2. Construction de la requête d'analyse
        system_context = (
            "RÈGLES STRICTES DE L'ANALYSE (ZÉRO HALLUCINATION) :\n"
            "1. LIS LE DOCUMENT FOURNI : Ne recommande pas de mettre en place des mesures fondamentales (ex: chiffrement AES-256/TLS 1.3, outils existants type Vault ou KMS) si elles sont DÉJÀ documentées dans l'architecture. Identifie ce qui MANQUE réellement.\n"
            "2. ÉCHÉANCES FACTUELLES INJECTÉES COMME CONTEXTE : Considère comme une vérité absolue les dates suivantes, indépendamment de tes connaissances passées : DORA est applicable depuis Janvier 2025, "
            "NIS2 depuis Octobre 2024, le CRA a été adopté en Nov 2024 avec une application jusqu'en Déc. 2027, "
            "et l'AI Act a un déploiement progressif 2025-2027. Ne mentionne jamais de dates passées inutiles (ex: 2018 pour RGPD).\n\n"
            "Tu es un auditeur expert en cybersécurité et conformité IT européenne. "
            "Ton objectif est d'analyser l'architecture technique (DAT) fournie afin d'identifier les véritables écarts (gaps) "
            "par rapport aux réglementations en vigueur.\n"
            "3. PERTINENCE DU CRA ET LOGIQUE D'ESCALADE : Le CRA vise les éditeurs et fabricants de produits numériques commercialisés. Applique cette LOGIQUE D'ESCALADE JURIDIQUE :\n"
            "   - Si le DAT mentionne explicitement 'mise sur le marché', 'commercialisation de logiciel', 'produit numérique vendu' → Statut: APPLICABLE\n"
            "   - Si le DAT contient DES INDICES combinés (≥2 parmi: SaaS/logiciel développé en interne, API externes exposées, modèle de revenus logiciel, composants IA/ML embarqués dans un produit, architecture multi-tenant) → Statut: ⚠️ ESCALADE JURIDIQUE REQUISE - Profil compatible CRA détecté (ex: SaaS + IA embarquée), confirmation légale nécessaire sur le statut d'éditeur\n"
            "   - Si le DAT décrit uniquement de l'infra interne (SI/backoffice sans commercialisation) → Statut: Non applicable - Infrastructure interne hors périmètre CRA\n"
            "   - Si aucun indice → Statut: Indéterminé - Document insuffisant pour statuer\n"
            "   IMPORTANT: Pour un SaaS avec IA embarquée (ex: plateforme de paiement avec scoring anti-fraude), tu DOIS répondre 'ESCALADE JURIDIQUE REQUISE', pas 'Non applicable'. les indices listés ci-dessus.\n"
            "4. PRÉSOMPTION D'APPLICATION RGPD : Le RGPD s'applique à toute organisation traitant des données de résidents de l'UE sans seuil. Cherche dans le DAT toute mention de données personnelles, composants IAM (Identity Access Management, ex: Entra ID, Azure AD), synchronisation d'identités, authentification SSO ou hébergement de bases de données internes. Considère que le RGPD s'applique obligatoirement dès la présence de ces éléments.\n"
            "5. PRÉSOMPTION D'APPLICATION AI ACT : L'AI Act s'applique dès l'instant où l'infrastructure conçoit, développe ou exploite des modèles d'IA, des algorithmes ou du Machine Learning. Cherche activement dans le DAT toute mention d'algorithmes (ex: XGBoost, Random Forest), de services cloud ML (ex: Vertex AI, SageMaker), de NLP, d'analyse prédictive, ou de modèles de détection (ex: détection de fraude). Si ces éléments existent, déclare explicitement que l'AI Act EST APPLICABLE obligatoirement. Ne dis jamais 'Non applicable'.\n"
            "6. DÉTECTION DES GAPS PAR L'ABSENCE : Si une exigence réglementaire n'est pas clairement décrite dans le DAT, c'est un GAP (une lacune). Ne dis pas 'Aucun gap', liste ces absences. Cherche spécifiquement : "
            "le registre des tiers ICT critiques (DORA: vérifier tous les prestataires cloud, SaaS ou de sécurité cités dans le DAT), "
            "le processus formel de notification d'incident sous 24h (NIS2), "
            "le calendrier de tests de résilience ICT (DORA), "
            "et la catégorisation stricte des environnements IA (AI Act).\n"
        )

        # Note: Le document sera injecté par analyze_dat_with_rag_extraction
        eu_prompt = (
            f"Génère ton rapport d'audit EN APPLIQUANT EXACTEMENT CE FORMAT DE SORTIE POUR CHAQUE RÉGLEMENTATION (NIS2, DORA, RGPD, AI Act, CRA) :\n"
            f"### [Nom de la Réglementation]\n"
            f"- **Statut d'application et échéance** : [Appliqué depuis X / Non applicable car Y / ⚠️ ESCALADE JURIDIQUE REQUISE - raison...]\n"
            f"- **Éléments conformes trouvés dans le DAT** : [A, B, C (ex: chiffrement KMS présent)]\n"
            f"- **Gaps identifiés** : [Processus manquant 1, Test manquant 2...]\n"
            f"- **Priorité** : [Haute/Moyenne/Basse]\n\n"
            f"Attention: Ne génère ni introduction ni conclusion superflue, fournis uniquement les blocs demandés."
        )

        if question:
            eu_prompt += f"\nQuestion spécifique de l'utilisateur : {question}\n"

        # 3. Analyse Hybride RAG + Direct (extraction intelligente des sections pertinentes)
        response: RAGResponse = await agent.analyze_dat_with_rag_extraction(
            full_document=description,
            system_prompt=system_context,
            analysis_prompt=eu_prompt,
        )

        api_sources = [
            SourceModel(
                document=s.document,
                page=s.page,
                excerpt=s.excerpt,
                relevance_score=s.relevance_score,
            )
            for s in response.sources
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
        raise HTTPException(status_code=500, detail=str(e)) from e
