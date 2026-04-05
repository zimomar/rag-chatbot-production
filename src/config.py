"""
Configuration centralisée du projet RAG Local.

Utilise pydantic-settings pour la gestion des variables d'environnement
avec validation et valeurs par défaut.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration de l'application RAG Local."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Ollama Configuration
    # -------------------------------------------------------------------------
    ollama_host: str = Field(
        default="http://localhost:11434",
        description="URL du serveur Ollama",
    )
    ollama_model: str = Field(
        default="mistral:7b-instruct-v0.3-q4_K_M",
        description="Modèle LLM pour la génération",
    )
    ollama_embed_model: str = Field(
        default="nomic-embed-text",
        description="Modèle pour les embeddings",
    )
    ollama_vision_model: str = Field(
        default="llava",
        description="Modèle vision pour l'analyse d'images (infrastructure)",
    )
    ollama_timeout: int = Field(
        default=120,
        description="Timeout en secondes pour les requêtes Ollama",
    )

    # -------------------------------------------------------------------------
    # ChromaDB Configuration
    # -------------------------------------------------------------------------
    chroma_host: str = Field(
        default="localhost",
        description="Host du serveur ChromaDB",
    )
    chroma_port: int = Field(
        default=8000,
        description="Port du serveur ChromaDB",
    )
    chroma_collection_name: str = Field(
        default="rag_documents",
        description="Nom de la collection ChromaDB",
    )

    # -------------------------------------------------------------------------
    # API Configuration
    # -------------------------------------------------------------------------
    api_host: str = Field(
        default="0.0.0.0",
        description="Host de l'API FastAPI",
    )
    api_port: int = Field(
        default=8000,
        description="Port de l'API FastAPI",
    )
    api_reload: bool = Field(
        default=False,
        description="Activer le hot reload (dev uniquement)",
    )

    # -------------------------------------------------------------------------
    # Document Processing
    # -------------------------------------------------------------------------
    chunk_size: int = Field(
        default=1000,
        ge=100,
        le=4000,
        description="Taille des chunks en caractères",
    )
    chunk_overlap: int = Field(
        default=200,
        ge=0,
        le=500,
        description="Chevauchement entre chunks en caractères",
    )
    retrieval_top_k: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Nombre de documents à récupérer pour le contexte",
    )
    max_file_size_mb: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Taille maximale d'un fichier uploadé en Mo",
    )

    # -------------------------------------------------------------------------
    # Authentication
    # -------------------------------------------------------------------------
    app_password: str = Field(
        default="",
        description="Mot de passe pour l'interface Streamlit (vide = pas d'auth)",
    )
    app_api_key: str = Field(
        default="",
        description="Clé API pour protéger les endpoints FastAPI (vide = pas d'auth)",
    )

    # -------------------------------------------------------------------------
    # Paths
    # -------------------------------------------------------------------------
    upload_dir: Path = Field(
        default=Path("uploads"),
        description="Répertoire pour les fichiers uploadés",
    )

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Niveau de log",
    )

    @field_validator("chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, v: int, info: Any) -> int:
        """Vérifie que l'overlap est inférieur à la taille du chunk."""
        chunk_size = info.data.get("chunk_size", 1000)
        if v >= chunk_size:
            raise ValueError(f"chunk_overlap ({v}) doit être inférieur à chunk_size ({chunk_size})")
        return v

    @field_validator("upload_dir")
    @classmethod
    def validate_upload_dir(cls, v: Path) -> Path:
        """Crée le répertoire d'upload s'il n'existe pas."""
        v.mkdir(parents=True, exist_ok=True)
        return v

    @property
    def chroma_url(self) -> str:
        """URL complète de ChromaDB."""
        return f"http://{self.chroma_host}:{self.chroma_port}"

    @property
    def max_file_size_bytes(self) -> int:
        """Taille maximale en bytes."""
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """
    Retourne l'instance des settings (singleton via cache).

    Utilise lru_cache pour ne charger les settings qu'une seule fois.
    En cas de besoin de recharger, appeler get_settings.cache_clear().

    Returns:
        Settings: Instance configurée des settings
    """
    return Settings()


# Alias pour import simplifié
settings = get_settings()
