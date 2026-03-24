"""
Découpage intelligent de documents en chunks.

Ce module utilise RecursiveCharacterTextSplitter pour créer des chunks
de taille contrôlée tout en respectant la structure du document.
"""

import logging
from dataclasses import dataclass, field
from typing import Sequence

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import settings
from src.ingestion.loader import Document

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """
    Représente un chunk de texte avec ses métadonnées.

    Attributes:
        content: Texte du chunk
        metadata: Métadonnées héritées du document + info chunk
    """

    content: str
    metadata: dict = field(default_factory=dict)

    @property
    def source(self) -> str:
        """Document source du chunk."""
        return self.metadata.get("source", "unknown")

    @property
    def chunk_index(self) -> int:
        """Index du chunk dans le document."""
        return self.metadata.get("chunk_index", 0)

    def __len__(self) -> int:
        """Longueur du chunk en caractères."""
        return len(self.content)

    def __repr__(self) -> str:
        """Représentation concise du chunk."""
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"Chunk(source={self.source}, index={self.chunk_index}, len={len(self)}, content='{preview}')"


class Chunker:
    """
    Découpe des documents en chunks de taille contrôlée.

    Utilise RecursiveCharacterTextSplitter avec des séparateurs hiérarchiques
    pour préserver au maximum la cohérence sémantique des chunks.

    Attributes:
        chunk_size: Taille cible des chunks en caractères
        chunk_overlap: Chevauchement entre chunks consécutifs
        separators: Liste ordonnée de séparateurs à essayer

    Exemple:
        >>> chunker = Chunker(chunk_size=500, chunk_overlap=100)
        >>> chunks = chunker.split(document)
        >>> print(f"Document découpé en {len(chunks)} chunks")
    """

    # Séparateurs ordonnés du plus large au plus fin
    DEFAULT_SEPARATORS = [
        "\n# ",  # Titre H1
        "\n## ",  # Titre H2
        "\n### ",  # Titre H3
        "\n\n\n",  # Triple saut = nouveau chapitre/section
        "\n\n",  # Double saut = nouveau paragraphe
        "\n",  # Simple saut = nouvelle ligne
        ". ",  # Fin de phrase
        " ",  # Espace
        "",  # Caractère par caractère (dernier recours)
    ]

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        separators: list[str] | None = None,
    ) -> None:
        """
        Initialise le chunker avec les paramètres de découpage.

        Args:
            chunk_size: Taille cible en caractères (défaut: settings.chunk_size)
            chunk_overlap: Chevauchement en caractères (défaut: settings.chunk_overlap)
            separators: Séparateurs personnalisés (défaut: DEFAULT_SEPARATORS)
        """
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap
        self.separators = separators or self.DEFAULT_SEPARATORS

        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) doit être < chunk_size ({self.chunk_size})"
            )

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=self.separators,
            length_function=len,
            is_separator_regex=False,
        )

        logger.info(
            f"Chunker initialisé: size={self.chunk_size}, overlap={self.chunk_overlap}"
        )

    def split(self, document: Document) -> list[Chunk]:
        """
        Découpe un document en chunks.

        Args:
            document: Document à découper

        Returns:
            Liste de chunks avec métadonnées

        Raises:
            ValueError: Si le document est vide
        """
        if not document.content.strip():
            raise ValueError(f"Document vide: {document.source}")

        logger.debug(f"Découpage de {document.source} ({len(document)} caractères)")

        # Utilise LangChain pour le découpage
        texts = self._splitter.split_text(document.content)

        chunks = []
        char_position = 0

        for i, text in enumerate(texts):
            # Calcule la position approximative dans le document original
            start_pos = document.content.find(text[:50], char_position)
            if start_pos == -1:
                start_pos = char_position

            chunk = Chunk(
                content=text,
                metadata={
                    **document.metadata,
                    "chunk_index": i,
                    "chunk_total": len(texts),
                    "char_start": start_pos,
                    "char_end": start_pos + len(text),
                },
            )
            chunks.append(chunk)

            # Met à jour la position pour la recherche suivante
            char_position = start_pos + len(text) - self.chunk_overlap

        logger.info(
            f"Document {document.source} découpé en {len(chunks)} chunks "
            f"(taille moyenne: {sum(len(c) for c in chunks) // len(chunks)} chars)"
        )

        return chunks

    def split_many(self, documents: Sequence[Document]) -> list[Chunk]:
        """
        Découpe plusieurs documents en chunks.

        Args:
            documents: Séquence de documents à découper

        Returns:
            Liste combinée de tous les chunks
        """
        all_chunks = []

        for doc in documents:
            try:
                chunks = self.split(doc)
                all_chunks.extend(chunks)
            except ValueError as e:
                logger.warning(f"Impossible de découper {doc.source}: {e}")
                continue

        logger.info(
            f"Total: {len(all_chunks)} chunks depuis {len(documents)} documents"
        )
        return all_chunks

    def estimate_chunks(self, content_length: int) -> int:
        """
        Estime le nombre de chunks pour un contenu donné.

        Utile pour prévoir l'espace de stockage ou le coût d'embedding.

        Args:
            content_length: Longueur du contenu en caractères

        Returns:
            Estimation du nombre de chunks
        """
        if content_length <= self.chunk_size:
            return 1

        effective_chunk_size = self.chunk_size - self.chunk_overlap
        return (content_length - self.chunk_overlap) // effective_chunk_size + 1
