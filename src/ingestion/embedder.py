"""
Génération d'embeddings via Ollama.

Ce module fournit une interface pour générer des vecteurs d'embedding
à partir de texte en utilisant le modèle nomic-embed-text via Ollama.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings
from src.ingestion.chunker import Chunk

logger = logging.getLogger(__name__)

# Dimension des embeddings nomic-embed-text
EMBEDDING_DIMENSION = 768


@dataclass
class EmbeddedChunk:
    """
    Chunk avec son vecteur d'embedding.

    Attributes:
        content: Texte du chunk
        embedding: Vecteur d'embedding (768 dimensions pour nomic-embed-text)
        metadata: Métadonnées du chunk
    """

    content: str
    embedding: list[float]
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Valide la dimension de l'embedding."""
        if len(self.embedding) != EMBEDDING_DIMENSION:
            logger.warning(
                f"Dimension inattendue: {len(self.embedding)} (attendu: {EMBEDDING_DIMENSION})"
            )

    @property
    def source(self) -> str:
        """Document source."""
        return self.metadata.get("source", "unknown")


class OllamaConnectionError(Exception):
    """Erreur de connexion au serveur Ollama."""

    pass


class EmbeddingError(Exception):
    """Erreur lors de la génération d'embedding."""

    pass


class Embedder:
    """
    Génère des embeddings via l'API Ollama.

    Utilise le modèle nomic-embed-text par défaut, avec retry automatique
    en cas d'erreur temporaire.

    Attributes:
        model: Nom du modèle d'embedding Ollama
        base_url: URL de base du serveur Ollama
        batch_size: Nombre de textes par batch

    Exemple:
        >>> embedder = Embedder()
        >>> embedded_chunks = embedder.embed_chunks(chunks)
        >>> print(f"Dimension: {len(embedded_chunks[0].embedding)}")
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        batch_size: int = 32,
        timeout: int | None = None,
    ) -> None:
        """
        Initialise l'embedder Ollama.

        Args:
            model: Modèle d'embedding (défaut: settings.ollama_embed_model)
            base_url: URL Ollama (défaut: settings.ollama_host)
            batch_size: Textes par batch (défaut: 32)
            timeout: Timeout en secondes (défaut: settings.ollama_timeout)
        """
        self.model = model or settings.ollama_embed_model
        self.base_url = (base_url or settings.ollama_host).rstrip("/")
        self.batch_size = batch_size
        self.timeout = timeout or settings.ollama_timeout

        self._client = httpx.Client(timeout=self.timeout)

        logger.info(f"Embedder initialisé: model={self.model}, url={self.base_url}")

    def __del__(self) -> None:
        """Ferme le client HTTP."""
        if hasattr(self, "_client"):
            self._client.close()

    def check_connection(self) -> bool:
        """
        Vérifie la connexion au serveur Ollama.

        Returns:
            True si le serveur est accessible
        """
        try:
            response = self._client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except httpx.RequestError:
            return False

    def check_model_available(self) -> bool:
        """
        Vérifie si le modèle d'embedding est disponible.

        Returns:
            True si le modèle est installé
        """
        try:
            response = self._client.get(f"{self.base_url}/api/tags")
            if response.status_code != 200:
                return False

            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]

            # Vérifie si le modèle (avec ou sans tag) est présent
            return any(
                self.model in name or name.startswith(self.model.split(":")[0])
                for name in model_names
            )
        except (httpx.RequestError, KeyError):
            return False

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def _embed_single(self, text: str) -> list[float]:
        """
        Génère l'embedding pour un seul texte.

        Args:
            text: Texte à encoder

        Returns:
            Vecteur d'embedding

        Raises:
            OllamaConnectionError: Si Ollama n'est pas accessible
            EmbeddingError: Si la génération échoue
        """
        try:
            response = self._client.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text,
                },
            )

            if response.status_code != 200:
                error_msg = response.text
                logger.error(f"Erreur Ollama: {response.status_code} - {error_msg}")
                raise EmbeddingError(f"Ollama error: {response.status_code}")

            data = response.json()
            embedding = data.get("embedding")

            if not embedding:
                raise EmbeddingError("Pas d'embedding dans la réponse")

            return embedding

        except httpx.ConnectError as e:
            logger.error(f"Impossible de se connecter à Ollama: {e}")
            raise OllamaConnectionError(
                f"Impossible de se connecter à Ollama ({self.base_url}). "
                "Vérifiez que le serveur est démarré."
            ) from e

    def embed_text(self, text: str) -> list[float]:
        """
        Génère l'embedding pour un texte.

        Args:
            text: Texte à encoder

        Returns:
            Vecteur d'embedding (768 dimensions)
        """
        return self._embed_single(text)

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """
        Génère les embeddings pour plusieurs textes.

        Traite les textes par batch pour optimiser les performances.

        Args:
            texts: Liste de textes à encoder

        Returns:
            Liste de vecteurs d'embedding
        """
        if not texts:
            return []

        embeddings = []
        total = len(texts)

        for i in range(0, total, self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_num = i // self.batch_size + 1
            total_batches = (total + self.batch_size - 1) // self.batch_size

            logger.debug(f"Embedding batch {batch_num}/{total_batches}")

            for text in batch:
                embedding = self._embed_single(text)
                embeddings.append(embedding)

        return embeddings

    def embed_chunk(self, chunk: Chunk) -> EmbeddedChunk:
        """
        Génère l'embedding pour un chunk.

        Args:
            chunk: Chunk à encoder

        Returns:
            EmbeddedChunk avec le vecteur d'embedding
        """
        embedding = self._embed_single(chunk.content)

        return EmbeddedChunk(
            content=chunk.content,
            embedding=embedding,
            metadata=chunk.metadata,
        )

    def embed_chunks(self, chunks: Sequence[Chunk]) -> list[EmbeddedChunk]:
        """
        Génère les embeddings pour plusieurs chunks.

        Args:
            chunks: Liste de chunks à encoder

        Returns:
            Liste d'EmbeddedChunks
        """
        if not chunks:
            return []

        logger.info(f"Embedding de {len(chunks)} chunks...")

        texts = [chunk.content for chunk in chunks]
        embeddings = self.embed_texts(texts)

        embedded_chunks = [
            EmbeddedChunk(
                content=chunk.content,
                embedding=embedding,
                metadata=chunk.metadata,
            )
            for chunk, embedding in zip(chunks, embeddings, strict=False)
        ]

        logger.info(f"Embedding terminé: {len(embedded_chunks)} chunks traités")

        return embedded_chunks
