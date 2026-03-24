"""
Module de retrieval (recherche par similarité).

Ce module gère l'interface avec ChromaDB pour stocker et rechercher
des documents par similarité vectorielle.
"""

from src.retrieval.store import VectorStore, SearchResult

__all__ = ["VectorStore", "SearchResult"]
