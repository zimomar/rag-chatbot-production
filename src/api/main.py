"""
API REST pour le chatbot RAG Local.
"""

import logging
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.agent.graph import RAGAgent, RAGResponse, Source
from src.config import settings
from src.ingestion.loader import DocumentLoader
from src.ingestion.chunker import Chunker
from src.ingestion.embedder import Embedder
from src.retrieval.store import VectorStore

# Configuration du logging
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RAG Local API",
    description="API pour un chatbot RAG 100% local",
    version="0.1.0",
)

# Initialisation des composants
loader = DocumentLoader()
chunker = Chunker()
embedder = Embedder()
vector_store = VectorStore()
agent = RAGAgent(vector_store=vector_store, embedder=embedder)

class QueryRequest(BaseModel):
    """Requête de question."""
    question: str

class SourceModel(BaseModel):
    """Modèle de source pour l'API."""
    document: str
    page: Optional[int]
    excerpt: str
    relevance_score: float

class QueryResponse(BaseModel):
    """Réponse de question."""
    answer: str
    sources: List[SourceModel]
    confidence: float

@app.get("/health")
def health_check():
    """Vérifie la santé de l'API et des services."""
    return {
        "status": "healthy",
        "ollama": embedder.check_connection(),
        "chromadb": vector_store.check_connection(),
    }

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload et indexation d'un document."""
    if file.size > settings.max_file_size_bytes:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux")

    try:
        # 1. Lecture
        content = await file.read()
        doc = loader.load_uploaded_file(content, file.filename)
        
        # 2. Chunking
        chunks = chunker.split(doc)
        
        # 3. Embedding
        embedded_chunks = embedder.embed_chunks(chunks)
        
        # 4. Stockage
        vector_store.add_documents(embedded_chunks)
        
        return {"status": "success", "chunks": len(chunks), "source": file.filename}
    except Exception as e:
        logger.error(f"Erreur d'indexation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query", response_model=QueryResponse)
async def query_agent(request: QueryRequest):
    """Pose une question au chatbot RAG."""
    try:
        response: RAGResponse = await agent.answer(request.question)
        
        # Mapping vers le modèle API
        api_sources = [
            SourceModel(
                document=s.document,
                page=s.page,
                excerpt=s.excerpt,
                relevance_score=s.relevance_score
            ) for s in response.sources
        ]
        
        return QueryResponse(
            answer=response.answer,
            sources=api_sources,
            confidence=response.confidence
        )
    except Exception as e:
        logger.error(f"Erreur agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents")
def list_documents():
    """Liste les documents indexés."""
    return {"documents": vector_store.list_sources()}

@app.delete("/documents/{filename}")
def delete_document(filename: str):
    """Supprime un document de la base."""
    count = vector_store.delete_by_source(filename)
    return {"status": "deleted", "chunks": count}
