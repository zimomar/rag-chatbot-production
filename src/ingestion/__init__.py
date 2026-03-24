"""
Module d'ingestion de documents.

Ce module gère le chargement, le découpage et l'embedding des documents
pour leur stockage dans le vector store.
"""

from src.ingestion.chunker import Chunker, Chunk
from src.ingestion.embedder import Embedder, EmbeddedChunk
from src.ingestion.loader import DocumentLoader, Document

__all__ = [
    "DocumentLoader",
    "Document",
    "Chunker",
    "Chunk",
    "Embedder",
    "EmbeddedChunk",
]
