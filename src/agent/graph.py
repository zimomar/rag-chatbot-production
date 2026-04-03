"""
Orchestration du flow RAG avec LangGraph.

Ce module définit le graphe d'états pour le cycle de vie d'une requête RAG :
Recherche (Retrieve) -> Génération (Generate) -> Citations (Cite).
"""

import logging
from dataclasses import dataclass, field
from typing import Any, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph

from src.config import settings
from src.ingestion.embedder import Embedder
from src.retrieval.store import SearchResult, VectorStore

logger = logging.getLogger(__name__)


@dataclass
class Source:
    """Représente une source citée dans la réponse."""
    document: str
    page: int | None = None
    excerpt: str = ""
    relevance_score: float = 0.0


@dataclass
class RAGResponse:
    """Réponse finale de l'agent RAG."""
    answer: str
    sources: list[Source] = field(default_factory=list)
    confidence: float = 0.0
    query: str = ""


class RAGState(TypedDict, total=False):
    """
    État du graphe LangGraph.
    
    Attributes:
        query: Question de l'utilisateur
        context: Chunks récupérés depuis le vector store
        answer: Réponse générée par le LLM
        sources: Liste des sources formatées
        confidence: Score de confiance global
        history: Historique de conversation pour multi-turn
    """
    query: str
    context: list[SearchResult]
    answer: str
    sources: list[Source]
    confidence: float
    history: list[dict] | None


class RAGAgent:
    """
    Agent RAG utilisant LangGraph pour orchestrer la recherche et la génération.
    """

    def __init__(
        self,
        vector_store: VectorStore = None,
        embedder: Embedder = None,
    ) -> None:
        """Initialise l'agent avec ses composants."""
        self.vector_store = vector_store or VectorStore()
        self.embedder = embedder or Embedder()
        self.base_url = settings.ollama_host.rstrip("/")

        # Construction du graphe
        workflow = StateGraph(RAGState)

        # Ajout des nœuds
        workflow.add_node("retrieve", self.retrieve)
        workflow.add_node("generate", self.generate)
        workflow.add_node("cite", self.cite)

        # Définition des liens
        workflow.add_edge(START, "retrieve")
        workflow.add_edge("retrieve", "generate")
        workflow.add_edge("generate", "cite")
        workflow.add_edge("cite", END)

        self.graph = workflow.compile()
        logger.info("Agent RAG initialisé avec LangGraph")

    def retrieve(self, state: RAGState) -> dict[str, Any]:
        """
        Nœud de recherche : récupère les documents pertinents.
        """
        query = state["query"]
        logger.info(f"Recherche de contexte pour: {query}")

        try:
            results = self.vector_store.search_by_text(
                query_text=query,
                embedder=self.embedder,
                top_k=settings.retrieval_top_k
            )
            return {"context": results}
        except Exception as e:
            logger.error(f"Erreur lors du retrieval: {e}")
            return {"context": []}

    def _build_prompt(
        self,
        query: str,
        context: list[SearchResult],
        history: list[dict] | None = None,
    ) -> str:
        """Construit le prompt complet pour le LLM."""
        # Optimization: Format XML ultra-compact (économise ~15% de tokens vs string)
        context_xml = "".join([
            f"<s i='{i+1}' src='{res.source}' pg='{res.metadata.get('page', 'N/A')}'>{res.content}</s>"
            for i, res in enumerate(context)
        ])

        # Instruction concise pour favoriser le KV Cache d'Ollama
        system_instruction = (
            "Assistant technique. Réponds via <ctx> uniquement. "
            "Cite comme [i]. Si info manquante, dis 'Information non trouvée'."
        )

        # Multi-turn: condense l'historique en contexte conversationnel
        history_block = ""
        if history:
            # Garde les N derniers échanges pour ne pas exploser le contexte
            recent = history[-6:]  # 3 derniers échanges (user+assistant)
            history_lines = []
            for msg in recent:
                role = "User" if msg["role"] == "user" else "Assistant"
                # Tronque les messages longs de l'historique
                content = msg["content"][:300]
                history_lines.append(f"{role}: {content}")
            history_block = "\nHistorique:\n" + "\n".join(history_lines) + "\n"

        return (
            f"Instruction: {system_instruction}\n"
            f"<ctx>{context_xml}</ctx>\n"
            f"{history_block}"
            f"Question: {query}\n"
            "Réponse:"
        )

    def generate(self, state: RAGState) -> dict[str, Any]:
        """
        Nœud de génération : appelle le LLM avec le contexte en format XML compact.
        """
        query = state["query"]
        context = state["context"]
        history = state.get("history")

        if not context:
            return {
                "answer": "Désolé, je n'ai pas trouvé d'informations dans les documents pour répondre à votre question.",
                "confidence": 0.0
            }

        full_prompt = self._build_prompt(query, context, history)

        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 1000,
                    }
                },
                timeout=settings.ollama_timeout
            )

            if response.status_code != 200:
                raise Exception(f"Erreur Ollama: {response.status_code}")

            result = response.json()
            answer = result.get("response", "")

            # Calcul de confiance basique
            avg_relevance = sum(res.relevance for res in context) / len(context)

            return {"answer": answer, "confidence": avg_relevance}

        except Exception as e:
            logger.error(f"Erreur lors de la génération: {e}")
            return {"answer": "Une erreur technique est survenue lors de la génération.", "confidence": 0.0}

    def cite(self, state: RAGState) -> dict[str, Any]:
        """
        Nœud de citations : extrait les sources basées sur les IDs XML [i].
        """
        answer = state["answer"]
        context = state["context"]

        sources = []
        for i, res in enumerate(context):
            # On cherche maintenant l'ID court [1], [2]...
            source_tag = f"[{i+1}]"

            if source_tag in answer or res.relevance > 0.8:
                sources.append(Source(
                    document=res.source,
                    page=res.metadata.get("page"),
                    excerpt=res.content[:200] + "...",
                    relevance_score=res.relevance
                ))

        return {"sources": sources}

    def describe_image(self, image_bytes: bytes) -> str:
        """
        Utilise le modèle vision d'Ollama pour décrire une image d'infrastructure.
        """
        import base64
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        prompt = (
            "Décris en détail cette infrastructure technique/IT. "
            "Identifie tous les composants visibles : serveurs, bases de données, "
            "réseaux, services cloud, APIs, systèmes de stockage, pare-feu, etc. "
            "Décris les connexions et flux de données entre les composants."
        )

        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": settings.ollama_vision_model,
                    "prompt": prompt,
                    "images": [image_b64],
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 2000},
                },
                timeout=settings.ollama_timeout,
            )
            if response.status_code != 200:
                raise Exception(f"Erreur Ollama vision: {response.status_code}")
            return response.json().get("response", "")
        except Exception as e:
            logger.error(f"Erreur lors de la description d'image: {e}")
            return ""

    async def answer(
        self,
        query: str,
        history: list[dict] | None = None,
    ) -> RAGResponse:
        """
        Point d'entrée principal pour poser une question.

        Args:
            query: Question de l'utilisateur
            history: Historique de conversation (optionnel, multi-turn)
        """
        initial_state: RAGState = {
            "query": query,
            "context": [],
            "answer": "",
            "sources": [],
            "confidence": 0.0,
            "history": history,
        }

        # Exécution du graphe
        final_state = self.graph.invoke(initial_state)

        return RAGResponse(
            answer=final_state["answer"],
            sources=final_state["sources"],
            confidence=final_state["confidence"],
            query=query
        )

    async def stream_answer(
        self,
        query: str,
        history: list[dict] | None = None,
    ):
        """
        Streaming : récupère les documents, puis stream la génération token par token.

        Yields des dicts:
            {"token": "..."} pour chaque token
            {"done": True, "sources": [...], "confidence": float} à la fin
        """
        # 1. Retrieval (synchrone, rapide)
        try:
            context = self.vector_store.search_by_text(
                query_text=query,
                embedder=self.embedder,
                top_k=settings.retrieval_top_k
            )
        except Exception as e:
            logger.error(f"Erreur de retrieval streaming: {e}")
            context = []

        if not context:
            yield {
                "token": "Désolé, je n'ai pas trouvé d'informations dans les documents pour répondre à votre question."
            }
            yield {"done": True, "sources": [], "confidence": 0.0}
            return

        full_prompt = self._build_prompt(query, context, history)

        # 2. Streaming generation
        full_answer = ""
        try:
            with httpx.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": full_prompt,
                    "stream": True,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 1000,
                    }
                },
                timeout=settings.ollama_timeout,
            ) as response:
                if response.status_code != 200:
                    yield {"token": "Erreur lors de la génération."}
                    yield {"done": True, "sources": [], "confidence": 0.0}
                    return

                import json as json_lib
                for line in response.iter_lines():
                    if line:
                        try:
                            data = json_lib.loads(line)
                            token = data.get("response", "")
                            if token:
                                full_answer += token
                                yield {"token": token}
                            if data.get("done", False):
                                break
                        except json_lib.JSONDecodeError:
                            continue

        except Exception as e:
            logger.error(f"Erreur streaming: {e}")
            yield {"token": "Erreur technique lors de la génération."}
            yield {"done": True, "sources": [], "confidence": 0.0}
            return

        # 3. Citation extraction
        avg_relevance = sum(res.relevance for res in context) / len(context)
        sources = []
        for i, res in enumerate(context):
            source_tag = f"[{i+1}]"
            if source_tag in full_answer or res.relevance > 0.8:
                sources.append(Source(
                    document=res.source,
                    page=res.metadata.get("page"),
                    excerpt=res.content[:200] + "...",
                    relevance_score=res.relevance
                ))

        yield {
            "done": True,
            "sources": [
                {
                    "document": s.document,
                    "page": s.page,
                    "excerpt": s.excerpt,
                    "relevance_score": s.relevance_score,
                }
                for s in sources
            ],
            "confidence": avg_relevance,
        }

    async def answer_with_context(self, query: str, extra_context: str = "") -> RAGResponse:
        """
        Point d'entrée avec contexte supplémentaire (ex: description d'infrastructure).
        Le contexte est préfixé à la query pour enrichir la recherche RAG.
        """
        enriched_query = f"{extra_context}\n\nQuestion: {query}" if extra_context else query
        return await self.answer(enriched_query)

