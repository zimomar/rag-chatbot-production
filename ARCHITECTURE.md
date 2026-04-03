# Architecture - RAG Local

Ce document décrit l'architecture technique du système RAG documentaire local.

## Vue d'Ensemble

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              UTILISATEUR                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
         ┌──────────────────┐            ┌──────────────────┐
         │   Streamlit UI   │            │   FastAPI        │
         │   (Port 8501)    │            │   (Port 8000)    │
         └────────┬─────────┘            └────────┬─────────┘
                  │                               │
                  └───────────────┬───────────────┘
                                  ▼
                    ┌─────────────────────────┐
                    │    LangGraph Agent      │
                    │  (Orchestration RAG)    │
                    └─────────────┬───────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
    ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
    │   Ingestion      │ │   Retrieval      │ │   Generation     │
    │   (Loader,       │ │   (ChromaDB)     │ │   (Ollama LLM)   │
    │    Chunker,      │ │                  │ │                  │
    │    Embedder)     │ │                  │ │                  │
    └────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘
             │                    │                    │
             ▼                    ▼                    ▼
    ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
    │   Ollama         │ │   ChromaDB       │ │   Ollama         │
    │   (Embeddings)   │ │   (Vector Store) │ │   (Mistral 7B)   │
    │   Port 11434     │ │   Port 8000      │ │   Port 11434     │
    └──────────────────┘ └──────────────────┘ └──────────────────┘
```

## Flows de Données

### Flow 1 : Ingestion de Document

```
PDF/Markdown → Loader → Chunker → Embedder → ChromaDB
```

**Étapes détaillées :**

1. **Upload** : L'utilisateur uploade un fichier via Streamlit ou l'API
2. **Validation** : Vérification du type MIME et de la taille (max 10 Mo)
3. **Loading** :
   - PDF : Extraction texte via PyMuPDF (page par page)
   - Markdown : Parsing avec métadonnées préservées
4. **Chunking** : Découpage avec `RecursiveCharacterTextSplitter`
   - Taille : 1000 caractères
   - Overlap : 200 caractères
   - Séparateurs : `["\n\n", "\n", ". ", " ", ""]`
5. **Embedding** : Génération des vecteurs via `nomic-embed-text` (768 dimensions)
6. **Storage** : Insertion dans ChromaDB avec métadonnées (source, page, chunk_id)

**Contrat d'interface :**

```python
# Input Loader
LoaderInput = Path | UploadedFile

# Output Loader → Input Chunker
@dataclass
class Document:
    content: str
    metadata: dict[str, Any]  # source, pages, created_at

# Output Chunker → Input Embedder
@dataclass
class Chunk:
    content: str
    metadata: dict[str, Any]  # source, page, chunk_index, char_start, char_end

# Output Embedder → Input Store
@dataclass
class EmbeddedChunk:
    content: str
    embedding: list[float]  # 768 dimensions
    metadata: dict[str, Any]
```

### Flow 2 : Query RAG

```
Question → Embedding → Retrieval → Context Building → LLM → Response + Citations
```

**Étapes détaillées :**

1. **Query Embedding** : La question utilisateur est transformée en vecteur
2. **Similarity Search** : Recherche des K chunks les plus similaires (défaut: 4)
3. **Context Building** : Assemblage des chunks en contexte structuré
4. **Prompt Engineering** : Construction du prompt avec instructions de citation
5. **LLM Generation** : Mistral 7B génère la réponse
6. **Citation Extraction** : Parsing des citations depuis la réponse
7. **Response Formatting** : Structure finale avec réponse + sources

**Contrat d'interface :**

```python
# Input Agent
@dataclass
class QueryInput:
    question: str
    top_k: int = 4

# Output Retrieval
@dataclass
class RetrievedContext:
    chunks: list[Chunk]
    scores: list[float]

# Output Agent
@dataclass
class RAGResponse:
    answer: str
    sources: list[Source]
    confidence: float

@dataclass
class Source:
    document: str
    page: int | None
    excerpt: str
    relevance_score: float
```

## Composants Détaillés

### 1. Ingestion (`src/ingestion/`)

#### `loader.py`
- **Responsabilité** : Extraire le texte brut des fichiers
- **Entrée** : Chemin fichier ou objet uploadé
- **Sortie** : `Document` avec contenu et métadonnées
- **Formats supportés** :
  - PDF : `pymupdf` (rapide, bon support Unicode)
  - Markdown : `markdown` (préserve la structure)
  - **DOCX** : `python-docx` (headings → hiérarchie MD, extraction tableaux)
  - **PPTX** : `python-pptx` (texte par slide avec marqueurs `[Slide N]`)
  - TXT : Texte brut

#### `chunker.py`
- **Responsabilité** : Découper en chunks cohérents
- **Stratégie** : `RecursiveCharacterTextSplitter` de LangChain
- **Paramètres** :
  - `chunk_size=1000` : Suffisant pour contexte, pas trop grand pour embeddings
  - `chunk_overlap=200` : Évite de couper les idées
  - Séparateurs hiérarchiques pour respecter la structure

#### `embedder.py`
- **Responsabilité** : Générer les vecteurs d'embedding
- **Modèle** : `nomic-embed-text` via Ollama
- **Dimensions** : 768
- **Batch processing** : Par lots de 32 pour optimiser

### 2. Retrieval (`src/retrieval/`)

#### `store.py`
- **Responsabilité** : Interface avec ChromaDB
- **Opérations** :
  - `add_documents()` : Insertion avec embeddings
  - `query()` : Recherche par similarité
  - `delete_collection()` : Suppression complète
  - `list_documents()` : Liste des sources indexées
- **Index** : HNSW (Hierarchical Navigable Small World)

### 3. Agent (`src/agent/`)

#### `graph.py`
- **Responsabilité** : Orchestration du flow RAG
- **Framework** : LangGraph
- **Nodes** :
  1. `retrieve` : Recherche dans ChromaDB
  2. `generate` : Appel LLM avec contexte + historique multi-turn
  3. `cite` : Extraction et formatage des citations
- **Edges** : Séquentiels (retrieve → generate → cite)
- **Méthodes additionnelles** :
  - `_build_prompt()` : Construction du prompt avec contexte XML + historique conversationnel
  - `stream_answer()` : Génération streaming (yield tokens via Ollama `stream: true`)
  - `describe_image()` : Description d'infrastructure via modèle vision

**Graph LangGraph :**

```
     ┌─────────┐
     │  START  │
     └────┬────┘
          │
          ▼
    ┌───────────┐
    │ retrieve  │  ← Recherche similarité
    └─────┬─────┘
          │
          ▼
    ┌───────────┐
    │ generate  │  ← Génération LLM (+ historique multi-turn)
    └─────┬─────┘
          │
          ▼
    ┌───────────┐
    │   cite    │  ← Formatage citations
    └─────┬─────┘
          │
          ▼
     ┌─────────┐
     │   END   │
     └─────────┘
```

### 4. API (`src/api/`)

#### `main.py`
- **Framework** : FastAPI v0.2.0
- **Middleware** : `APIKeyMiddleware` (authentification optionnelle via `X-API-Key`)
- **Endpoints** :
  - `POST /upload` : Upload et indexation de document (PDF, MD, DOCX, PPTX)
  - `POST /query` : Question RAG avec historique multi-turn optionnel
  - `POST /query/stream` : Question RAG en streaming SSE (token par token)
  - `GET /health` : Health check
  - `GET /documents` : Liste des documents indexés
  - `DELETE /documents/{id}` : Suppression d'un document
  - `POST /feedback` : Enregistrer un feedback 👍/👎
  - `GET /feedback` : Lister les feedbacks
  - `POST /compliance-report` : Générer un rapport de conformité multi-réglementation
  - `POST /analyze-infrastructure` : Analyser un schéma via modèle vision

### 5. UI (`src/ui/`)

#### `app.py`
- **Framework** : Streamlit
- **Composants** :
  - **Login gate** : Page d'authentification (si `APP_PASSWORD` configuré)
  - **Sidebar** : Upload de fichiers, liste des documents, toggle thème, historique conversations
  - **Tab Chat** : Interface de chat avec streaming SSE + multi-turn + feedback 👍/👎
  - **Tab Infrastructure** : Analyse de schémas d'infrastructure
  - **Tab Conformité** : Génération de rapports de conformité (NIS2, DORA, RGPD, AI Act)
  - **État** : Session state pour historique conversation et auth

## Choix Techniques

### Pourquoi nomic-embed-text ?

| Critère | nomic-embed-text | all-MiniLM-L6 | BGE-base |
|---------|------------------|---------------|----------|
| Dimensions | 768 | 384 | 768 |
| Performance FR | Bonne | Moyenne | Très bonne |
| Vitesse | Rapide | Très rapide | Moyen |
| Via Ollama | Oui | Non (sentence-transformers) | Non |
| Taille | 274 Mo | 80 Mo | 440 Mo |

**Décision** : nomic-embed-text offre le meilleur compromis qualité/intégration. Disponible directement via Ollama, ce qui simplifie l'architecture (un seul service pour LLM et embeddings).

### Pourquoi RecursiveCharacterTextSplitter ?

| Stratégie | Avantages | Inconvénients |
|-----------|-----------|---------------|
| Fixed size | Simple, prévisible | Coupe au milieu des phrases |
| Sentence | Respecte les phrases | Chunks de taille variable |
| Recursive | Hiérarchique, adaptatif | Plus complexe |
| Semantic | Meilleur contexte | Lent, imprévisible |

**Décision** : RecursiveCharacterTextSplitter est le meilleur compromis. Il essaie de couper aux paragraphes d'abord, puis aux phrases, puis aux mots. Résultat : chunks cohérents et de taille contrôlée.

### Pourquoi Mistral 7B Q4_K_M ?

| Modèle | RAM | Qualité | Vitesse |
|--------|-----|---------|---------|
| Mistral 7B Q4_K_M | ~6 Go | Bonne | ~10 tok/s |
| Mistral 7B Q8 | ~8 Go | Très bonne | ~7 tok/s |
| Llama 3 8B Q4 | ~6 Go | Très bonne | ~8 tok/s |
| Phi-3 Mini | ~3 Go | Correcte | ~15 tok/s |

**Décision** : Mistral 7B Q4_K_M offre la meilleure qualité pour une consommation RAM acceptable (reste de la marge pour ChromaDB et l'app). La quantization Q4_K_M préserve bien la qualité.

### Pourquoi ChromaDB ?

| Solution | Avantages | Inconvénients |
|----------|-----------|---------------|
| ChromaDB | Simple, embedded ou client/serveur | Moins scalable |
| Qdrant | Performant, filtres avancés | Plus complexe |
| Weaviate | Hybride keyword/vector | Lourd |
| FAISS | Très rapide | Pas de persistance native |

**Décision** : ChromaDB est le plus simple à déployer et suffisant pour 10-15 documents. Mode client/serveur permet l'isolation dans Docker.

## Gestion des Erreurs

### Stratégie par Couche

1. **Ingestion** :
   - Fichier corrompu → Exception claire + log
   - Timeout Ollama → Retry avec backoff (3 tentatives)

2. **Retrieval** :
   - ChromaDB down → Health check échoue, 503
   - Collection vide → Retourne message informatif

3. **Agent** :
   - Ollama timeout → Retry avec backoff
   - Contexte vide → Réponse "Je n'ai pas trouvé d'information"

4. **API** :
   - Validation Pydantic → 422 avec détails
   - Erreur interne → 500 avec ID de corrélation

## Limites et Évolutions

### Limites Actuelles

1. **Pas d'OCR** : PDF scannés (images) non traités
2. **Pas de reranking** : Résultats bruts de similarité
3. **Mono-concurrent** : 1 requête LLM à la fois (limitation CPU Ollama)

### Réalisé en V2 ✅

1. **✅ Streaming SSE** : Réponses token par token
2. **✅ Multi-turn** : Mémoire conversationnelle (3 derniers échanges)
3. **✅ Authentification** : Mot de passe UI + clé API
4. **✅ DOCX/PPTX** : Formats Word et PowerPoint supportés
5. **✅ Feedback loop** : Boutons 👍/👎 avec stockage
6. **✅ Rapport de conformité** : Génération automatique multi-réglementation

### Évolutions Futures (V3)

1. **Reranking** : Cross-encoder pour améliorer la pertinence
2. **Hybrid search** : Combiner BM25 + vector search
3. **OCR** : Tesseract pour PDF scannés
4. **Metadata filtering** : Filtres par date, type, etc.
5. **Multi-tenant** : Espaces documentaires isolés par utilisateur

## Ressources et Contraintes

### VPS Hetzner CX42

| Ressource | Disponible | Utilisé |
|-----------|------------|---------|
| vCPU | 8 shared | ~4 (inference) |
| RAM | 16 Go | ~12 Go max |
| Stockage | 160 Go NVMe | ~25 Go |

**Répartition RAM :**
- Ollama + Mistral : 8 Go
- ChromaDB : 1 Go
- Application : 1 Go
- Système : 2 Go
- Marge : 4 Go

### Performances Attendues

- **Indexation** : ~2-3 secondes par page PDF
- **Query** : ~3-5 secondes (retrieval + génération)
- **Throughput** : 1 query concurrent (limitation Ollama)
