"""
API REST pour le chatbot RAG Local.
"""

import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
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
# CORS Middleware (pour permettre les appels depuis le frontend)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production, spécifier les domaines autorisés
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


class GraphNodeModel(BaseModel):
    """Modèle de nœud dans le graphe d'infrastructure."""

    id: str
    name: str
    type: str
    controls: list[str]


class GraphEdgeModel(BaseModel):
    """Modèle d'arête dans le graphe d'infrastructure."""

    from_: str
    to: str
    protocol: str

    class Config:
        fields = {"from_": "from"}


class ComplianceScoreModel(BaseModel):
    """Scores de conformité par réglementation pour un nœud."""

    NIS2: float
    DORA: float
    RGPD: float
    AI_Act: float
    CRA: float


class GraphAnalysisResponse(BaseModel):
    """Réponse d'analyse de graphe d'infrastructure."""

    success: bool
    nodes: list[GraphNodeModel]
    edges: list[GraphEdgeModel]
    compliance_scores_by_node: dict[str, ComplianceScoreModel]
    error: str | None = None


@app.post("/analyze-infrastructure-graph", response_model=GraphAnalysisResponse)
async def analyze_infrastructure_graph(
    file: UploadFile = File(...),
) -> GraphAnalysisResponse:
    """
    Extrait la topologie d'infrastructure d'un DAT et calcule les scores de conformité par nœud.
    Retourne un graphe JSON avec nodes, edges et compliance scores.
    """
    try:
        content = await file.read()
        filename = (file.filename or "").lower()

        # 1. Extract text from document
        if filename.endswith((".docx", ".pdf")):
            doc = loader.load_uploaded_file(content, filename)
            document_text = doc.content
            logger.info(f"Extracted DAT document: {len(document_text)} chars")
        else:
            raise HTTPException(
                status_code=422,
                detail="Format non supporté. Utilisez .docx ou .pdf pour les DATs.",
            )

        # 2. Extract architecture graph
        graph_result = await agent.extract_architecture_graph(document_text)

        if not graph_result["success"]:
            return GraphAnalysisResponse(
                success=False,
                nodes=[],
                edges=[],
                compliance_scores_by_node={},
                error=graph_result.get("error", "Échec de l'extraction du graphe"),
            )

        # 3. Extract controls for all nodes via single LLM call
        all_controls = _extract_all_controls_via_llm(graph_result["nodes"], document_text)

        # 4. Calculate compliance scores per node
        compliance_scores = {}
        for node in graph_result["nodes"]:
            node_id = node["id"]
            controls = all_controls.get(node_id, set())

            scores = _analyze_node_compliance(node, controls)
            compliance_scores[node_id] = ComplianceScoreModel(**scores)

        # 5. Format response
        nodes = [GraphNodeModel(**node) for node in graph_result["nodes"]]
        edges = [
            GraphEdgeModel(from_=edge["from"], to=edge["to"], protocol=edge.get("protocol", "unknown"))
            for edge in graph_result["edges"]
        ]

        return GraphAnalysisResponse(
            success=True,
            nodes=nodes,
            edges=edges,
            compliance_scores_by_node=compliance_scores,
            error=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur analyse graphe infrastructure: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


def _filter_applicable_regulations(node: dict[str, Any]) -> dict[str, bool]:
    """
    Détermine quelles réglementations s'appliquent à un nœud donné.

    Args:
        node: Nœud du graphe avec type et nom

    Returns:
        Dictionnaire {regulation: is_applicable}
    """
    node_type = node.get("type", "").lower()
    node_name = node.get("name", "").lower()

    # AI Act: only for AI/ML systems
    ai_keywords = ["ai", "ml", "model", "prediction", "machine learning", "neural", "intelligence"]
    is_ai_system = any(kw in node_type for kw in ai_keywords) or any(kw in node_name for kw in ai_keywords)

    # DORA: only for financial/critical operational systems
    dora_types = ["database", "api", "service", "payment", "transaction", "banking"]
    is_dora_applicable = any(t in node_type for t in dora_types)

    # RGPD: if handles personal data (check for common patterns)
    rgpd_keywords = ["user", "customer", "personal", "auth", "identity", "profile", "account", "payment", "transaction", "banking"]
    handles_personal_data = any(kw in node_type for kw in rgpd_keywords) or any(kw in node_name for kw in rgpd_keywords)

    # NIS2 and CRA: apply to all
    return {
        "NIS2": True,
        "DORA": is_dora_applicable,
        "RGPD": handles_personal_data,
        "AI_Act": is_ai_system,
        "CRA": True,
    }


def _extract_all_controls_via_llm(nodes: list[dict[str, Any]], document_text: str) -> dict[str, set[str]]:
    """
    Extrait les contrôles pour TOUS les nœuds via 1 seul appel LLM.

    Args:
        nodes: Liste des nœuds du graphe
        document_text: Contenu complet du DAT

    Returns:
        Dict {node_id: set(controls)}
    """
    if not nodes:
        return {}

    # Create temporary index once
    temp_chunker = Chunker()
    temp_embedder = Embedder()
    temp_store = VectorStore(collection_name=f"temp_all_{uuid4().hex[:8]}")

    try:
        from src.ingestion.loader import Document
        temp_doc = Document(content=document_text, source="dat_analysis")

        chunks = temp_chunker.split(temp_doc)
        embedded_chunks = temp_embedder.embed_chunks(chunks)
        temp_store.add_documents(embedded_chunks)

        # Get relevant chunks for each node
        nodes_with_chunks = []
        for node in nodes:
            node_id = node["id"]
            node_name = node.get("name", "")
            node_type = node.get("type", "")

            search_query = f"{node_name} {node_type} security controls sécurité"
            results = temp_store.search_by_text(
                query_text=search_query,
                embedder=temp_embedder,
                top_k=3
            )

            chunks_text = "\n".join([r.content[:300] for r in results])
            nodes_with_chunks.append({
                "id": node_id,
                "name": node_name,
                "type": node_type,
                "chunks": chunks_text,
            })

        # Build prompt for LLM
        nodes_desc = "\n\n".join([
            f"- ID: {n['id']}\n  Nom: {n['name']}\n  Type: {n['type']}\n  Extraits:\n{n['chunks']}"
            for n in nodes_with_chunks
        ])

        system_prompt = (
            "Tu es un expert en sécurité. Analyse les extraits de documentation pour chaque composant "
            "et identifie TOUS les contrôles de sécurité mentionnés (TLS, mTLS, encryption, backup, MFA, "
            "firewall, monitoring, SIEM, etc.). Retourne UNIQUEMENT un JSON valide."
        )

        user_prompt = (
            f"Pour chaque composant ci-dessous, liste les contrôles de sécurité trouvés dans les extraits.\n\n"
            f"Composants:\n{nodes_desc}\n\n"
            f"Retourne UNIQUEMENT ce JSON (sans texte avant/après):\n"
            f'{{"node_id_1": ["control1", "control2"], "node_id_2": [...], ...}}'
        )

        # Call LLM
        response = httpx.post(
            f"{settings.ollama_host}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 2000},
            },
            timeout=60.0,
        )

        if response.status_code != 200:
            logger.error(f"LLM error: {response.status_code}")
            return {n["id"]: set(n.get("controls", [])) for n in nodes}

        result = response.json()
        answer = result.get("message", {}).get("content", "")

        # Parse JSON
        import json as json_lib
        json_str = answer.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        controls_dict = json_lib.loads(json_str)

        # Normalize and convert to sets
        def normalize_control(ctrl: str) -> str:
            """Normalize control name: lowercase, replace spaces with underscores."""
            return ctrl.lower().strip().replace(" ", "_").replace("-", "_")

        result_dict = {}
        for node in nodes:
            node_id = node["id"]
            llm_controls = {normalize_control(c) for c in controls_dict.get(node_id, [])}
            graph_controls = {normalize_control(c) for c in node.get("controls", [])}
            result_dict[node_id] = llm_controls | graph_controls

        logger.info(f"Extracted controls for {len(result_dict)} nodes via LLM")
        return result_dict

    except Exception as e:
        logger.error(f"Error in LLM control extraction: {e}")
        return {n["id"]: set(n.get("controls", [])) for n in nodes}
    finally:
        try:
            temp_store.client.delete_collection(temp_store.collection_name)
        except Exception:
            pass


def _extract_controls_from_rag(node: dict[str, Any], document_text: str) -> set[str]:
    """
    Utilise RAG pour extraire les contrôles de sécurité spécifiques à un nœud depuis le DAT.

    Args:
        node: Nœud du graphe
        document_text: Contenu complet du DAT

    Returns:
        Ensemble des contrôles détectés pour ce nœud
    """
    node_name = node.get("name", "")
    node_type = node.get("type", "")

    # Create temporary chunks and index
    temp_chunker = Chunker()
    temp_embedder = Embedder()
    temp_store = VectorStore(collection_name=f"temp_node_{uuid4().hex[:8]}")

    try:
        # Create a temporary document
        from src.ingestion.loader import Document
        temp_doc = Document(content=document_text, source=f"dat_{node_name}")

        # Chunk and embed
        chunks = temp_chunker.split(temp_doc)
        embedded_chunks = temp_embedder.embed_chunks(chunks)
        temp_store.add_documents(embedded_chunks)

        # Build type-specific search terms
        type_terms = {
            "network": "firewall IDS IPS segmentation VLAN",
            "firewall": "règles filtrage pare-feu zones",
            "database": "backup sauvegarde chiffrement accès",
            "api": "authentification TLS rate-limiting",
            "storage": "chiffrement backup réplication",
            "auth": "MFA SSO IAM authentification",
            "load_balancer": "répartition charge haute disponibilité failover health check",
        }
        specific_terms = type_terms.get(node_type, "")

        # Search for node-specific security information
        search_query = f"{node_name} {node_type} {specific_terms} security controls encryption authentication monitoring backup access control"
        results = temp_store.search_by_text(
            query_text=search_query,
            embedder=temp_embedder,
            top_k=5  # Increased from 3
        )

        # Extract controls from the chunks
        controls = set()
        control_keywords = {
            # Encryption/TLS
            "TLS", "mTLS", "SSL", "encryption", "chiffrement", "AES-256", "TLS 1.3",
            # Monitoring
            "logging", "monitoring", "journalisation", "surveillance", "SIEM", "audit",
            # Incident
            "incident_response", "gestion incidents", "24h_notification",
            # Backup/DR
            "backup", "sauvegarde", "disaster_recovery", "DR", "continuity", "continuité", "failover",
            "high availability", "haute disponibilité", "HA", "load balancing", "répartition charge",
            "health check", "redondance", "redundancy",
            # Network security
            "firewall", "pare-feu", "IDS", "IPS", "WAF", "VLAN", "segmentation",
            "network segmentation", "segmentation réseau", "DMZ", "VPN", "NAC",
            "network access control", "contrôle accès réseau",
            # Access control
            "MFA", "SSO", "IAM", "RBAC", "access_control", "contrôle accès", "authentification", "authentication",
            # RGPD
            "pseudonymization", "pseudonymisation", "anonymization", "anonymisation", "data_minimization", "minimisation",
            "DPO", "privacy_by_design", "DPIA", "PIA",
            # Vulnerability/CRA
            "vulnerability_scanning", "scan vulnérabilités", "vulnérabilité", "patch_management",
            "gestion correctifs", "CVE_monitoring", "CVE",
            "SAST", "DAST", "secure_SDLC", "SDLC sécurisé",
            "SBOM", "supply_chain_security", "sécurité chaîne approvisionnement",
            "dependency_scanning", "scan dépendances",
            # DORA
            "resilience_testing", "test résilience", "chaos_testing",
            "vendor_management", "gestion fournisseurs", "third_party_audit", "audit tiers",
            # AI Act
            "documentation", "model_card", "transparency", "transparence",
            "bias_monitoring", "biais", "fairness_testing", "équité", "SHAP",
            "human_oversight", "supervision humaine", "human_in_loop",
            "data_governance", "gouvernance données", "data_quality", "qualité données", "lineage"
        }

        # Mapping FR → EN canonical names
        keyword_mapping = {
            "chiffrement": "encryption",
            "journalisation": "logging",
            "surveillance": "monitoring",
            "gestion incidents": "incident_response",
            "sauvegarde": "backup",
            "continuité": "continuity",
            "haute disponibilité": "high availability",
            "répartition charge": "load balancing",
            "redondance": "redundancy",
            "pare-feu": "firewall",
            "segmentation réseau": "network segmentation",
            "contrôle accès réseau": "network access control",
            "contrôle accès": "access_control",
            "authentification": "authentication",
            "pseudonymisation": "pseudonymization",
            "anonymisation": "anonymization",
            "minimisation": "data_minimization",
            "vulnérabilité": "vulnerability_scanning",
            "scan vulnérabilités": "vulnerability_scanning",
            "gestion correctifs": "patch_management",
            "SDLC sécurisé": "secure_SDLC",
            "sécurité chaîne approvisionnement": "supply_chain_security",
            "scan dépendances": "dependency_scanning",
            "test résilience": "resilience_testing",
            "gestion fournisseurs": "vendor_management",
            "audit tiers": "third_party_audit",
            "transparence": "transparency",
            "biais": "bias_monitoring",
            "équité": "fairness_testing",
            "supervision humaine": "human_oversight",
            "gouvernance données": "data_governance",
            "qualité données": "data_quality",
        }

        # Scan chunks for control keywords
        for result in results:
            content_lower = result.content.lower()
            for keyword in control_keywords:
                if keyword.lower() in content_lower:
                    # Use canonical English name
                    canonical = keyword_mapping.get(keyword, keyword)
                    controls.add(canonical)

        # Combine with LLM-extracted controls
        llm_controls = set(node.get("controls", []))
        combined = controls | llm_controls

        logger.info(f"RAG extracted {len(controls)} controls for node {node_name}, LLM had {len(llm_controls)}, combined: {combined}")
        return combined

    except Exception as e:
        logger.error(f"Error in RAG control extraction for node {node_name}: {e}")
        # Fallback to existing controls from LLM extraction
        return set(node.get("controls", []))
    finally:
        # Cleanup temporary collection
        try:
            temp_store.client.delete_collection(temp_store.collection_name)
        except Exception:
            pass


def _analyze_node_compliance(node: dict[str, Any], controls: set[str]) -> dict[str, float]:
    """
    Analyse la conformité d'un nœud avec ses contrôles détectés.

    Args:
        node: Nœud du graphe
        controls: Ensemble des contrôles de sécurité détectés

    Returns:
        Dictionnaire des scores par réglementation
    """

    # Determine applicable regulations
    applicable_regs = _filter_applicable_regulations(node)

    # Calculate scores based on extracted controls
    scores = {}

    if applicable_regs["NIS2"]:
        scores["NIS2"] = _calculate_nis2_score(node, controls)
    else:
        scores["NIS2"] = 100.0  # N/A = 100%

    if applicable_regs["DORA"]:
        scores["DORA"] = _calculate_dora_score(node, controls)
    else:
        scores["DORA"] = 100.0

    if applicable_regs["RGPD"]:
        scores["RGPD"] = _calculate_rgpd_score(node, controls)
    else:
        scores["RGPD"] = 100.0

    if applicable_regs["AI_Act"]:
        scores["AI_Act"] = _calculate_ai_act_score(node, controls)
    else:
        scores["AI_Act"] = 100.0

    if applicable_regs["CRA"]:
        scores["CRA"] = _calculate_cra_score(node, controls)
    else:
        scores["CRA"] = 100.0

    logger.info(f"Node {node.get('name')} compliance scores: {scores}")
    return scores


def _calculate_nis2_score(node: dict[str, Any], controls: set[str]) -> float:
    """Calcule le score NIS2 basé sur les contrôles de cybersécurité."""
    score = 0.0
    max_score = 5.0

    # Normalize controls for comparison
    controls_lower = {c.lower() for c in controls}

    # Encryption/TLS
    if any(c in controls_lower for c in ["tls", "mtls", "encryption", "tls_1.3", "aes_256", "ssl"]):
        score += 1.0

    # Monitoring/logging
    if any(c in controls_lower for c in ["logging", "monitoring", "siem"]):
        score += 1.0

    # Incident response
    if any(c in controls_lower for c in ["incident_response", "24h_notification"]):
        score += 1.0

    # Backup/disaster recovery
    if any(c in controls_lower for c in ["backup", "disaster_recovery", "dr", "failover", "high_availability", "redundancy"]):
        score += 1.0

    # Network security
    if any(c in controls_lower for c in ["firewall", "ids", "ips", "idps", "waf", "network_segmentation", "vlan", "dmz", "vpn", "nac", "network_access_control"]):
        score += 1.0

    return (score / max_score) * 100


def _calculate_dora_score(node: dict[str, Any], controls: set[str]) -> float:
    """Calcule le score DORA basé sur la résilience opérationnelle."""
    score = 0.0
    max_score = 4.0

    controls_lower = {c.lower() for c in controls}

    # ICT resilience testing
    if any(c in controls_lower for c in ["resilience_testing", "chaos_testing"]):
        score += 1.0

    # Third-party risk management
    if any(c in controls_lower for c in ["vendor_management", "third_party_audit"]):
        score += 1.0

    # Continuity/backup
    if any(c in controls_lower for c in ["backup", "continuity", "failover", "high_availability", "redundancy"]):
        score += 1.0

    # Incident management
    if any(c in controls_lower for c in ["incident_management", "incident_response"]):
        score += 1.0

    return (score / max_score) * 100


def _calculate_rgpd_score(node: dict[str, Any], controls: set[str]) -> float:
    """Calcule le score RGPD basé sur la protection des données."""
    score = 0.0
    max_score = 5.0

    controls_lower = {c.lower() for c in controls}

    # Encryption
    if any(c in controls_lower for c in ["encryption", "tls", "mtls", "aes_256", "ssl"]):
        score += 1.0

    # Access control/IAM
    if any(c in controls_lower for c in ["iam", "mfa", "sso", "access_control", "rbac", "authentication"]):
        score += 1.0

    # Data minimization/pseudonymization
    if any(c in controls_lower for c in ["pseudonymization", "anonymization", "data_minimization"]):
        score += 1.0

    # DPO/privacy by design
    if any(c in controls_lower for c in ["dpo", "privacy_by_design", "dpia"]):
        score += 1.0

    # Audit logs
    if any(c in controls_lower for c in ["audit_logs", "logging"]):
        score += 1.0

    return (score / max_score) * 100


def _calculate_ai_act_score(node: dict[str, Any], controls: set[str]) -> float:
    """Calcule le score AI Act basé sur la gouvernance IA."""
    score = 0.0
    max_score = 4.0

    controls_lower = {c.lower() for c in controls}

    # Documentation/transparency
    if any(c in controls_lower for c in ["documentation", "model_card", "transparency"]):
        score += 1.0

    # Bias monitoring
    if any(c in controls_lower for c in ["bias_monitoring", "fairness_testing", "shap"]):
        score += 1.0

    # Human oversight
    if any(c in controls_lower for c in ["human_oversight", "human_in_loop"]):
        score += 1.0

    # Data governance
    if any(c in controls_lower for c in ["data_governance", "data_quality", "lineage"]):
        score += 1.0

    return (score / max_score) * 100


def _calculate_cra_score(node: dict[str, Any], controls: set[str]) -> float:
    """Calcule le score CRA basé sur la sécurité des produits numériques."""
    score = 0.0
    max_score = 3.0

    controls_lower = {c.lower() for c in controls}

    # Vulnerability management
    if any(c in controls_lower for c in ["vulnerability_scanning", "patch_management", "cve_monitoring", "vulnerability", "vuln"]):
        score += 1.0

    # Secure development
    if any(c in controls_lower for c in ["sast", "dast", "secure_sdlc", "sdlc"]):
        score += 1.0

    # SBOM/supply chain
    if any(c in controls_lower for c in ["sbom", "supply_chain_security", "dependency_scanning"]):
        score += 1.0

    return (score / max_score) * 100


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
            "3. PERTINENCE DU CRA : Le CRA vise les fabricants et éditeurs de produits numériques mis sur le marché européen, PAS les utilisateurs de solutions tierces. DISTINGUE D'ABORD LE RÔLE :\n"
            "   • FABRICANT/ÉDITEUR (in scope CRA) : Développe des logiciels/composants, met sur le marché des produits numériques, commercialise des solutions propriétaires\n"
            "   • UTILISATEUR (out of scope CRA) : Achète des solutions tierces, déploie des SaaS/PaaS externes (Salesforce, Azure AD, Vertex AI, etc.), consomme des services cloud\n"
            "   RÈGLE : Si le DAT décrit uniquement des achats, déploiements et configurations de solutions tierces (ex: 'utilise Vertex AI', 'déploie Azure AD', 'consomme API Stripe'), l'organisation est UTILISATRICE → CRA Non applicable.\n"
            "   \n"
            "   Applique ensuite cette logique stricte :\n"
            "   - Si le DAT mentionne EXPLICITEMENT 'mise sur le marché', 'commercialisation de produit numérique', 'vente de logiciel' → Statut: Applicable\n"
            "   - Si le DAT contient des INDICES de développement propriétaire (SaaS développé en interne, API propriétaires exposées, IA développée et embarquée dans un produit) MAIS SANS mention explicite de commercialisation → Statut: Indéterminé - Le DAT ne permet pas de confirmer si l'entreprise met des produits numériques sur le marché. Cette qualification juridique nécessite une analyse contractuelle et commerciale hors périmètre du document technique.\n"
            "   - Si le DAT décrit uniquement de l'infrastructure interne (SI, backoffice, sans produit commercialisé) → Statut: Non applicable\n"
            "   IMPORTANT: Un SaaS DÉVELOPPÉ avec IA EMBARQUÉE DÉVELOPPÉE (ex: plateforme de paiement avec scoring XGBoost propriétaire) est un INDICE de fabricant, pas une preuve. Réponds 'Indéterminé'. MAIS si l'IA est simplement UTILISÉE via API tierce (ex: 'appelle API OpenAI', 'utilise Vertex AI'), c'est un UTILISATEUR → Non applicable.\n"
            "4. PÉRIMÈTRE SECTORIEL DORA : DORA (Règlement EU 2022/2554) s'applique UNIQUEMENT aux entités financières réglementées. Cherche dans le DAT des indices du secteur d'activité :\n"
            "   • APPLICABLE si le DAT mentionne explicitement : banque, établissement de crédit, assurance, gestionnaire d'actifs, plateforme de paiement réglementée, infrastructure de marché financier, prestataire de services de paiement agréé\n"
            "   • NON APPLICABLE si le DAT décrit : industrie manufacturière (aciérie, usine, production), commerce/retail (e-commerce, logistique), télécoms, énergie, santé, transport, administration publique, ou tout autre secteur non financier\n"
            "   • INDÉTERMINÉ si aucun indice sectoriel clair dans le DAT\n"
            "   RÈGLE STRICTE : En l'absence de mention explicite d'activité financière réglementée, conclure 'Non applicable - DORA vise exclusivement le secteur financier (banques, assurances, gestionnaires d'actifs). Le DAT ne permet pas de confirmer que l'organisation opère dans ce périmètre.'\n"
            "5. PRÉSOMPTION D'APPLICATION RGPD : Le RGPD s'applique à toute organisation traitant des données de résidents de l'UE sans seuil. Cherche dans le DAT toute mention de données personnelles, composants IAM (Identity Access Management, ex: Entra ID, Azure AD), synchronisation d'identités, authentification SSO ou hébergement de bases de données internes. Considère que le RGPD s'applique obligatoirement dès la présence de ces éléments.\n"
            "6. PRÉSOMPTION D'APPLICATION AI ACT : L'AI Act s'applique dès l'instant où l'infrastructure conçoit, développe ou exploite des modèles d'IA, des algorithmes ou du Machine Learning. Cherche activement dans le DAT toute mention d'algorithmes (ex: XGBoost, Random Forest), de services cloud ML (ex: Vertex AI, SageMaker), de NLP, d'analyse prédictive, ou de modèles de détection (ex: détection de fraude). Si ces éléments existent, déclare explicitement que l'AI Act EST APPLICABLE obligatoirement. Ne dis jamais 'Non applicable'.\n"
            "7. DÉTECTION DES GAPS PAR L'ABSENCE : Si une exigence réglementaire n'est pas clairement décrite dans le DAT, c'est un GAP (une lacune). Ne dis pas 'Aucun gap', liste ces absences. Cherche spécifiquement : "
            "le registre des tiers ICT critiques (DORA: vérifier tous les prestataires cloud, SaaS ou de sécurité cités dans le DAT), "
            "le processus formel de notification d'incident sous 24h (NIS2), "
            "le calendrier de tests de résilience ICT (DORA), "
            "et la catégorisation stricte des environnements IA (AI Act).\n"
        )

        # Note: Le document sera injecté par analyze_dat_with_rag_extraction
        eu_prompt = (
            f"Génère ton rapport d'audit EN APPLIQUANT EXACTEMENT CE FORMAT DE SORTIE POUR CHAQUE RÉGLEMENTATION (NIS2, DORA, RGPD, AI Act, CRA) :\n"
            f"### [Nom de la Réglementation]\n"
            f"- **Statut d'application et échéance** : [Appliqué depuis X / Non applicable car Y / Indéterminé - raison...]\n"
            f"- **Éléments conformes trouvés dans le DAT** : [A, B, C (ex: chiffrement KMS présent)]\n"
            f"- **Gaps identifiés** : [Processus manquant 1, Test manquant 2...]\n"
            f"- **Priorité** : [Haute/Moyenne/Basse]\n\n"
            f"RÈGLE DE COHÉRENCE PRIORITÉ :\n"
            f"- Haute : Gaps critiques identifiés ET réglementation applicable\n"
            f"- Moyenne : Gaps mineurs ou améliorations recommandées\n"
            f"- Basse : Aucun gap identifié (éléments conformes uniquement) OU réglementation non applicable/indéterminée\n"
            f"IMPORTANT: Si tu écris 'Aucun gap' ou liste uniquement des éléments conformes, la priorité DOIT être Basse, pas Moyenne.\n\n"
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
