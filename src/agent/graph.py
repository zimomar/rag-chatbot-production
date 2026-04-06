"""
Orchestration du flow RAG avec LangGraph.

Ce module définit le graphe d'états pour le cycle de vie d'une requête RAG :
Recherche (Retrieve) -> Génération (Generate) -> Citations (Cite).
"""

import logging
from collections.abc import AsyncGenerator
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
    search_query: str | None
    system_prompt: str | None
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
        vector_store: VectorStore | None = None,
        embedder: Embedder | None = None,
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
        query = state.get("search_query") or state["query"]
        logger.info(f"Recherche de contexte pour: {query[:100]}...")

        try:
            results = self.vector_store.search_by_text(
                query_text=query, embedder=self.embedder, top_k=settings.retrieval_top_k
            )
            return {"context": results}
        except Exception as e:
            logger.error(f"Erreur lors du retrieval: {e}")
            return {"context": []}

    def _build_messages(
        self,
        query: str,
        context: list[SearchResult],
        system_prompt: str | None = None,
        history: list[dict] | None = None,
    ) -> list[dict]:
        """Construit le tableau de messages pour le modèle Chat."""
        # Optimization: Format XML ultra-compact
        context_xml = "".join(
            [
                f"<s i='{i + 1}' src='{res.source}' pg='{res.metadata.get('page', 'N/A')}'>{res.content}</s>"
                for i, res in enumerate(context)
            ]
        )

        if system_prompt:
            final_system = f"{system_prompt}\n\nContexte réglementaire documentaire (RAG):\n<ctx>{context_xml}</ctx>"
        else:
            final_system = (
                "Assistant technique. Réponds via <ctx> uniquement. "
                "Cite comme [i]. Si info manquante, dis 'Information non trouvée'.\n\n"
                f"<ctx>{context_xml}</ctx>"
            )

        messages = [{"role": "system", "content": final_system}]

        # Multi-turn: condense l'historique
        if history:
            recent = history[-6:]
            for msg in recent:
                content = msg["content"][:500]  # Tronqué pour préserver le contexte
                messages.append({"role": msg.get("role", "user"), "content": content})

        messages.append({"role": "user", "content": query})
        return messages

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
                "confidence": 0.0,
            }

        messages = self._build_messages(query, context, state.get("system_prompt"), history)

        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 1000,
                        "num_ctx": 8192,
                    },
                },
                timeout=settings.ollama_timeout,
            )

            if response.status_code != 200:
                raise Exception(f"Erreur Ollama: {response.status_code}")

            result = response.json()
            answer = result.get("message", {}).get("content", "")

            # Log metrics (Telemetry)
            eval_count = result.get("eval_count", 0)
            total_duration = result.get("total_duration", 0) / 1e9  # nanoseconds to seconds
            model_name = result.get("model", settings.ollama_model)
            logger.info(
                f"[LLM Telemetry] Model: {model_name} | Tokens: {eval_count} | Duration: {total_duration:.2f}s"
            )

            # Calcul de confiance basique
            avg_relevance = sum(res.relevance for res in context) / len(context)

            return {"answer": answer, "confidence": avg_relevance}

        except httpx.TimeoutException as e:
            logger.error(f"Timeout LLM (> {settings.ollama_timeout}s): {e}")
            return {
                "answer": f"Le modèle LLM a mis trop de temps à répondre (> {settings.ollama_timeout}s). Essayez de raccourcir la requête ou réessayez.",
                "confidence": 0.0,
            }
        except Exception as e:
            logger.error(f"Erreur lors de la génération: {e}")
            return {
                "answer": f"Une erreur technique est survenue: {str(e)[:150]}",
                "confidence": 0.0,
            }

    def cite(self, state: RAGState) -> dict[str, Any]:
        """
        Nœud de citations : extrait les sources basées sur les IDs XML [i].
        """
        answer = state["answer"]
        context = state["context"]

        sources = []
        for i, res in enumerate(context):
            # On cherche maintenant l'ID court [1], [2]...
            source_tag = f"[{i + 1}]"

            if source_tag in answer or res.relevance > 0.8:
                sources.append(
                    Source(
                        document=res.source,
                        page=res.metadata.get("page"),
                        excerpt=res.content[:200] + "...",
                        relevance_score=res.relevance,
                    )
                )

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
            result: str = response.json().get("response", "")
            return result
        except Exception as e:
            logger.error(f"Erreur lors de la description d'image: {e}")
            return ""

    async def answer(
        self,
        query: str,
        history: list[dict] | None = None,
        search_query: str | None = None,
        system_prompt: str | None = None,
    ) -> RAGResponse:
        """
        Point d'entrée principal pour poser une question.

        Args:
            query: Question de l'utilisateur
            history: Historique de conversation (optionnel, multi-turn)
        """
        initial_state: RAGState = {
            "query": query,
            "search_query": search_query,
            "system_prompt": system_prompt,
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
            query=query,
        )

    async def stream_answer(
        self,
        query: str,
        history: list[dict] | None = None,
        search_query: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Streaming : récupère les documents, puis stream la génération token par token.

        Yields des dicts:
            {"token": "..."} pour chaque token
            {"done": True, "sources": [...], "confidence": float} à la fin
        """
        # 1. Retrieval (synchrone, rapide)
        try:
            context = self.vector_store.search_by_text(
                query_text=search_query or query, embedder=self.embedder, top_k=settings.retrieval_top_k
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

        messages = self._build_messages(query, context, system_prompt, history)

        # 2. Streaming generation
        full_answer = ""
        try:
            with httpx.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 1000,
                        "num_ctx": 8192,
                    },
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
                            token = data.get("message", {}).get("content", "")
                            if token:
                                full_answer += token
                                yield {"token": token}
                            if data.get("done", False):
                                # Log metrics (Telemetry)
                                eval_count = data.get("eval_count", 0)
                                total_duration = data.get("total_duration", 0) / 1e9
                                model_name = data.get("model", settings.ollama_model)
                                logger.info(
                                    f"[LLM Telemetry] Model: {model_name} | Tokens: {eval_count} | Duration: {total_duration:.2f}s"
                                )
                                break
                        except json_lib.JSONDecodeError:
                            continue

        except httpx.TimeoutException as e:
            logger.error(f"Timeout LLM streaming (> {settings.ollama_timeout}s): {e}")
            yield {
                "token": f"\n\n[Erreur: Temps de réponse dépassé (> {settings.ollama_timeout}s)]"
            }
            yield {"done": True, "sources": [], "confidence": 0.0}
            return
        except Exception as e:
            logger.error(f"Erreur streaming: {e}")
            yield {"token": f"\n\n[Erreur technique: {str(e)[:100]}]"}
            yield {"done": True, "sources": [], "confidence": 0.0}
            return

        # 3. Citation extraction
        avg_relevance = sum(res.relevance for res in context) / len(context)
        sources = []
        for i, res in enumerate(context):
            source_tag = f"[{i + 1}]"
            if source_tag in full_answer or res.relevance > 0.8:
                sources.append(
                    Source(
                        document=res.source,
                        page=res.metadata.get("page"),
                        excerpt=res.content[:200] + "...",
                        relevance_score=res.relevance,
                    )
                )

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

    async def generate_direct(self, prompt: str, system_prompt: str | None = None) -> RAGResponse:
        """
        Appel direct au LLM sans recherche RAG, idéal pour analyser un document entier passé en mémoire
        sans risquer de contaminer le contexte avec des chunks aléatoires d'autres documents.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 1200,
                        "num_ctx": 8192,  # Maximum stable context limit to avoid OOM 500s
                    },
                },
                timeout=settings.ollama_timeout,
            )
            response.raise_for_status()
            result = response.json()
            answer = result.get("message", {}).get("content", "")

            eval_count = result.get("eval_count", 0)
            total_duration = result.get("total_duration", 0) / 1e9
            model_name = result.get("model", settings.ollama_model)
            logger.info(f"[LLM Telemetry Direct] Model: {model_name} | Tokens: {eval_count} | Duration: {total_duration:.2f}s")

            return RAGResponse(answer=answer, sources=[], confidence=1.0, query=prompt)
        except Exception as e:
            logger.error(f"Erreur lors du generate_direct: {e}")
            raise

    async def analyze_dat_with_rag_extraction(
        self,
        full_document: str,
        system_prompt: str,
        analysis_prompt: str,
    ) -> RAGResponse:
        """
        Analyse hybride d'un DAT avec extraction RAG intelligente.

        Stratégie :
        1. Chunke le document complet (évite la troncature brutale)
        2. Indexe temporairement dans ChromaDB avec une source unique
        3. Extrait les chunks pertinents pour chaque réglementation via RAG
        4. Construit un contexte enrichi avec les meilleurs chunks
        5. Analyse via generate_direct avec contexte optimisé
        6. Nettoie l'index temporaire
        7. Calcule une confiance réelle basée sur la pertinence des chunks

        Args:
            full_document: Contenu complet du DAT (non tronqué)
            system_prompt: Prompt système pour l'analyse
            analysis_prompt: Prompt d'analyse (sans le document)

        Returns:
            RAGResponse avec analyse et confiance calculée
        """
        from src.ingestion.chunker import Chunker
        from src.ingestion.loader import Document
        import uuid

        temp_source = f"temp_dat_{uuid.uuid4().hex[:8]}"

        try:
            # 1. Chunking intelligent du document complet
            logger.info(f"[DAT Analysis] Chunking document ({len(full_document)} chars)")
            chunker = Chunker(chunk_size=1000, chunk_overlap=200)
            doc = Document(content=full_document, metadata={"source": temp_source})
            chunks = chunker.split(doc)
            logger.info(f"[DAT Analysis] Created {len(chunks)} chunks")

            # 2. Embedding et indexation temporaire
            logger.info("[DAT Analysis] Embedding chunks")
            embedded_chunks = self.embedder.embed_chunks(chunks)
            self.vector_store.add_documents(embedded_chunks)
            logger.info(f"[DAT Analysis] Indexed {len(embedded_chunks)} chunks with source={temp_source}")

            # 3. Requêtes RAG ciblées pour chaque réglementation
            queries = {
                "AI_Act": "intelligence artificielle machine learning ML algorithmes modèles XGBoost Random Forest Vertex AI SageMaker prédictif détection fraude scoring SHAP feature",
                "DORA": "résilience ICT tiers critiques fournisseurs cloud tests incident notification continuité backup disaster recovery",
                "RGPD": "données personnelles GDPR RGPD DPO consentement privacy IAM identités Entra Azure AD SSO authentification",
                "NIS2": "cybersécurité incident sécurité réseau information directive cyber attaque notification 24h",
                "CRA": "produits numériques mise sur le marché composants logiciels commercialisation",
            }

            all_relevant_chunks = []
            relevance_scores = []

            for regulation, query in queries.items():
                logger.info(f"[DAT Analysis] Searching for {regulation} related content")
                results = self.vector_store.search_by_text(
                    query_text=query,
                    embedder=self.embedder,
                    top_k=3,  # Top 3 chunks par réglementation
                    where={"source": temp_source}  # Filtrer uniquement le DAT temporaire
                )

                if results:
                    logger.info(f"[DAT Analysis] {regulation}: found {len(results)} relevant chunks (relevance: {[f'{r.relevance:.2f}' for r in results]})")
                    all_relevant_chunks.extend(results)
                    relevance_scores.extend([r.relevance for r in results])
                else:
                    logger.warning(f"[DAT Analysis] {regulation}: no relevant chunks found")

            # 4. Déduplication et tri par pertinence
            seen_ids = set()
            unique_chunks = []
            for chunk in sorted(all_relevant_chunks, key=lambda x: x.relevance, reverse=True):
                if chunk.id not in seen_ids:
                    seen_ids.add(chunk.id)
                    unique_chunks.append(chunk)

            logger.info(f"[DAT Analysis] Kept {len(unique_chunks)} unique chunks after deduplication")

            # 5. Construction du contexte enrichi
            if unique_chunks:
                enriched_context = "\n\n".join([
                    f"[Section {i+1} - Pertinence: {chunk.relevance:.0%}]\n{chunk.content}"
                    for i, chunk in enumerate(unique_chunks[:15])  # Max 15 meilleurs chunks
                ])

                # Calcul de la confiance moyenne
                avg_confidence = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0
                logger.info(f"[DAT Analysis] Average chunk relevance: {avg_confidence:.2%}")
            else:
                # Fallback: utiliser le début du document si aucun chunk pertinent
                logger.warning("[DAT Analysis] No relevant chunks found, using document head")
                enriched_context = full_document[:20000]
                avg_confidence = 0.3  # Confiance basse

            # 6. Prompt final avec contexte enrichi
            final_prompt = (
                f"Voici les sections pertinentes extraites du DAT :\n\n"
                f"```text\n{enriched_context}\n```\n\n"
                f"{analysis_prompt}"
            )

            # 7. Analyse directe avec contexte optimisé
            logger.info(f"[DAT Analysis] Calling LLM with enriched context ({len(enriched_context)} chars)")
            response = await self.generate_direct(
                prompt=final_prompt,
                system_prompt=system_prompt
            )

            # 8. Surcharge de la confiance avec la vraie valeur calculée
            response.confidence = avg_confidence

            # 9. Ajout des sources
            response.sources = [
                Source(
                    document=temp_source,
                    excerpt=chunk.content[:200],
                    relevance_score=chunk.relevance
                )
                for chunk in unique_chunks[:5]  # Top 5 sources
            ]

            logger.info(f"[DAT Analysis] Analysis complete. Confidence: {avg_confidence:.0%}")

            return response

        finally:
            # 10. Nettoyage de l'index temporaire
            try:
                self.vector_store.delete_by_source(temp_source)
                logger.info(f"[DAT Analysis] Cleaned up temporary index {temp_source}")
            except Exception as e:
                logger.error(f"[DAT Analysis] Failed to cleanup temp index: {e}")

