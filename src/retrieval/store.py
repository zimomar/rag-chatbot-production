"""
Interface avec ChromaDB pour le stockage et la recherche vectorielle.

Ce module encapsule toutes les opérations avec ChromaDB : ajout de documents,
recherche par similarité, et gestion des collections.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.config import settings
from src.ingestion.embedder import EmbeddedChunk

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """
    Résultat d'une recherche par similarité.

    Attributes:
        content: Texte du chunk trouvé
        metadata: Métadonnées du chunk
        score: Score de similarité (distance, plus petit = plus similaire)
        id: Identifiant unique du chunk dans la base
    """

    content: str
    metadata: dict = field(default_factory=dict)
    score: float = 0.0
    id: str = ""

    @property
    def source(self) -> str:
        """Document source."""
        return self.metadata.get("source", "unknown")

    @property
    def relevance(self) -> float:
        """
        Score de pertinence normalisé (0-1, plus grand = plus pertinent).

        Convertit la distance en score de pertinence.
        """
        # ChromaDB utilise la distance L2, on la convertit en similarité
        return max(0.0, 1.0 - self.score / 2.0)


class VectorStoreError(Exception):
    """Erreur générique du vector store."""

    pass


class CollectionNotFoundError(VectorStoreError):
    """Collection non trouvée."""

    pass


class VectorStore:
    """
    Interface avec ChromaDB pour le stockage vectoriel.

    Gère une collection ChromaDB avec des opérations CRUD sur les documents
    et la recherche par similarité.

    Attributes:
        collection_name: Nom de la collection ChromaDB
        host: Host du serveur ChromaDB
        port: Port du serveur ChromaDB

    Exemple:
        >>> store = VectorStore()
        >>> store.add_documents(embedded_chunks)
        >>> results = store.search("Ma question", top_k=4)
    """

    def __init__(
        self,
        collection_name: str | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        """
        Initialise la connexion à ChromaDB.

        Args:
            collection_name: Nom de la collection (défaut: settings.chroma_collection_name)
            host: Host ChromaDB (défaut: settings.chroma_host)
            port: Port ChromaDB (défaut: settings.chroma_port)
        """
        self.collection_name = collection_name or settings.chroma_collection_name
        self.host = host or settings.chroma_host
        self.port = port or settings.chroma_port

        # Connexion au serveur ChromaDB (Forçage tenant/database pour stabilité 0.5.x)
        self._client = chromadb.HttpClient(
            host=self.host,
            port=self.port,
            tenant="default_tenant",
            database="default_database",
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # Récupère ou crée la collection
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name
        )

        logger.info(
            f"VectorStore connecté: {self.host}:{self.port}, "
            f"collection={self.collection_name}"
        )

    def check_connection(self) -> bool:
        """
        Vérifie la connexion à ChromaDB.

        Returns:
            True si le serveur est accessible
        """
        try:
            self._client.heartbeat()
            return True
        except Exception:
            return False

    @property
    def count(self) -> int:
        """Nombre de documents dans la collection."""
        return self._collection.count()

    def add_documents(
        self,
        chunks: Sequence[EmbeddedChunk],
        ids: Sequence[str] | None = None,
    ) -> list[str]:
        """
        Ajoute des chunks embedés à la collection.

        Args:
            chunks: Liste de chunks avec embeddings
            ids: IDs personnalisés (auto-générés si non fournis)

        Returns:
            Liste des IDs des documents ajoutés

        Raises:
            VectorStoreError: Si l'ajout échoue
        """
        if not chunks:
            logger.warning("Aucun chunk à ajouter")
            return []

        # Génère des IDs si non fournis
        if ids is None:
            ids = [str(uuid4()) for _ in chunks]

        # Prépare les données pour ChromaDB
        documents = [chunk.content for chunk in chunks]
        embeddings = [chunk.embedding for chunk in chunks]
        metadatas = [self._sanitize_metadata(chunk.metadata) for chunk in chunks]

        try:
            self._collection.add(
                ids=list(ids),
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )

            logger.info(f"Ajouté {len(chunks)} chunks à la collection")
            return list(ids)

        except Exception as e:
            logger.error(f"Erreur lors de l'ajout: {e}")
            raise VectorStoreError(f"Impossible d'ajouter les documents: {e}") from e

    def _sanitize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """
        Nettoie les métadonnées pour ChromaDB.

        ChromaDB n'accepte que str, int, float, bool comme valeurs.

        Args:
            metadata: Métadonnées brutes

        Returns:
            Métadonnées nettoyées
        """
        sanitized = {}
        for key, value in metadata.items():
            if isinstance(value, str | int | float | bool):
                sanitized[key] = value
            elif value is None:
                continue
            else:
                # Convertit en string
                sanitized[key] = str(value)
        return sanitized

    def search(
        self,
        query_embedding: list[float],
        top_k: int | None = None,
        where: dict | None = None,
    ) -> list[SearchResult]:
        """
        Recherche les chunks les plus similaires à un embedding.

        Args:
            query_embedding: Vecteur de la requête
            top_k: Nombre de résultats (défaut: settings.retrieval_top_k)
            where: Filtre sur les métadonnées

        Returns:
            Liste de SearchResult ordonnés par pertinence
        """
        top_k = top_k or settings.retrieval_top_k

        if self.count == 0:
            logger.warning("Collection vide, aucune recherche possible")
            return []

        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, self.count),
                where=where,
                include=["documents", "metadatas", "distances"],
            )

            search_results = []

            # ChromaDB retourne des listes de listes
            ids = results.get("ids", [[]])[0]
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            for i, doc_id in enumerate(ids):
                search_results.append(
                    SearchResult(
                        content=documents[i] if documents else "",
                        metadata=metadatas[i] if metadatas else {},
                        score=distances[i] if distances else 0.0,
                        id=doc_id,
                    )
                )

            logger.debug(f"Recherche: {len(search_results)} résultats")
            return search_results

        except Exception as e:
            logger.error(f"Erreur lors de la recherche: {e}")
            raise VectorStoreError(f"Erreur de recherche: {e}") from e

    def search_by_text(
        self,
        query_text: str,
        embedder: Any,  # Évite import circulaire
        top_k: int | None = None,
    ) -> list[SearchResult]:
        """
        Recherche par texte (génère l'embedding automatiquement).

        Args:
            query_text: Texte de la requête
            embedder: Instance de l'Embedder
            top_k: Nombre de résultats

        Returns:
            Liste de SearchResult
        """
        query_embedding = embedder.embed_text(query_text)
        return self.search(query_embedding, top_k=top_k)

    def list_sources(self) -> list[str]:
        """
        Liste tous les documents sources dans la collection.

        Returns:
            Liste des noms de fichiers sources uniques
        """
        if self.count == 0:
            return []

        try:
            # Récupère toutes les métadonnées
            results = self._collection.get(include=["metadatas"])
            metadatas = results.get("metadatas", [])

            sources = set()
            for metadata in metadatas:
                if metadata and "source" in metadata:
                    sources.add(metadata["source"])

            return sorted(sources)

        except Exception as e:
            logger.error(f"Erreur lors du listage: {e}")
            return []

    def delete_by_source(self, source: str) -> int:
        """
        Supprime tous les chunks d'un document source.

        Args:
            source: Nom du fichier source

        Returns:
            Nombre de chunks supprimés
        """
        try:
            # Suppression directe via filtre
            self._collection.delete(where={"source": source})
            logger.info(f"Supprimé tous les chunks de la source: {source}")
            # Note: Chroma ne retourne plus le nombre supprimé directement
            return 1

        except Exception as e:
            logger.error(f"Erreur lors de la suppression: {e}")
            raise VectorStoreError(f"Impossible de supprimer: {e}") from e

    def clear(self) -> None:
        """
        Vide complètement la collection.

        Attention: Cette opération est irréversible.
        """
        try:
            self._client.delete_collection(self.collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "l2"},
            )
            logger.info(f"Collection {self.collection_name} vidée")

        except Exception as e:
            logger.error(f"Erreur lors du vidage: {e}")
            raise VectorStoreError(f"Impossible de vider la collection: {e}") from e

    def get_stats(self) -> dict[str, Any]:
        """
        Retourne des statistiques sur la collection.

        Returns:
            Dictionnaire avec les stats
        """
        sources = self.list_sources()

        return {
            "collection_name": self.collection_name,
            "total_chunks": self.count,
            "total_documents": len(sources),
            "sources": sources,
        }
