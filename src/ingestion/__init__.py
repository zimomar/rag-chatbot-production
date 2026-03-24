"""
Module d'ingestion de documents.

Ce module gère le chargement, le découpage et l'embedding des documents
pour leur stockage dans le vector store.
"""

from src.ingestion.chunker import Chunk, Chunker
from src.ingestion.embedder import EmbeddedChunk, Embedder
from src.ingestion.loader import Document, DocumentLoader

__all__ = [
    "DocumentLoader",
    "Document",
    "Chunker",
    "Chunk",
    "Embedder",
    "EmbeddedChunk",
]
