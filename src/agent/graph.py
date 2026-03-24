"""
Orchestration du flow RAG avec LangGraph.

Ce module définit le graphe d'états pour le cycle de vie d'une requête RAG :
Recherche (Retrieve) -> Génération (Generate) -> Citations (Cite).
"""

import logging
from dataclasses import dataclass, field
from typing import Annotated, Any, Dict, List, TypedDict, Union

import httpx
from langgraph.graph import END, StateGraph, START

from src.config import settings
from src.ingestion.embedder import Embedder
from src.retrieval.store import SearchResult, VectorStore

logger = logging.getLogger(__name__)


@dataclass
class Source:
    """Représente une source citée dans la réponse."""
    document: str
    page: Union[int, None] = None
    excerpt: str = ""
    relevance_score: float = 0.0


@dataclass
class RAGResponse:
    """Réponse finale de l'agent RAG."""
    answer: str
    sources: List[Source] = field(default_factory=list)
    confidence: float = 0.0
    query: str = ""


class RAGState(TypedDict):
    """
    État du graphe LangGraph.
    
    Attributes:
        query: Question de l'utilisateur
        context: Chunks récupérés depuis le vector store
        answer: Réponse générée par le LLM
        sources: Liste des sources formatées
        confidence: Score de confiance global
    """
    query: str
    context: List[SearchResult]
    answer: str
    sources: List[Source]
    confidence: float


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

    def retrieve(self, state: RAGState) -> Dict[str, Any]:
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

    def generate(self, state: RAGState) -> Dict[str, Any]:
        """
        Nœud de génération : appelle le LLM avec le contexte en format XML compact.
        """
        query = state["query"]
        context = state["context"]
        
        if not context:
            return {
                "answer": "Désolé, je n'ai pas trouvé d'informations dans les documents pour répondre à votre question.",
                "confidence": 0.0
            }

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

        full_prompt = (
            f"Instruction: {system_instruction}\n"
            f"<ctx>{context_xml}</ctx>\n"
            f"Question: {query}\n"
            "Réponse:"
        )

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

    def cite(self, state: RAGState) -> Dict[str, Any]:
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

    async def answer(self, query: str) -> RAGResponse:
        """
        Point d'entrée principal pour poser une question.
        """
        initial_state = {
            "query": query,
            "context": [],
            "answer": "",
            "sources": [],
            "confidence": 0.0
        }
        
        # Exécution du graphe (synchrone ici pour simplifier)
        # Note: LangGraph supporte async, mais Ollama sur CPU est le goulot d'étranglement
        final_state = self.graph.invoke(initial_state)
        
        return RAGResponse(
            answer=final_state["answer"],
            sources=final_state["sources"],
            confidence=final_state["confidence"],
            query=query
        )
