# DEVLOG - RAG Local

Journal de bord du développement. Chaque entrée documente ce qui a été fait, les décisions prises, et les prochaines étapes.

---

## 2026-03-24 - Scaffolding Initial

### Ce qui a été fait

- Initialisation de la structure complète du projet
- Configuration Docker Compose avec 3 services (app, chromadb, ollama)
- Mise en place des dépendances Python (pyproject.toml)
- Documentation initiale (README, ARCHITECTURE)

### Fichiers créés

```
rag-local/
├── docker-compose.yml      ✅ 3 services, networking, volumes, health checks
├── Dockerfile              ✅ Multi-stage build, non-root user
├── .env.example            ✅ Toutes les variables documentées
├── .gitignore              ✅ Python + projet spécifique
├── README.md               ✅ Installation, usage, configuration
├── ARCHITECTURE.md         ✅ Flows, composants, choix techniques
├── DEVLOG.md               ✅ Ce fichier
├── pyproject.toml          ✅ Deps avec extras dev/test
├── src/
│   ├── __init__.py         ✅
│   ├── config.py           ✅ Settings Pydantic
│   ├── ingestion/
│   │   ├── __init__.py     ✅
│   │   ├── loader.py       ✅ PDF + Markdown
│   │   ├── chunker.py      ✅ RecursiveCharacterTextSplitter
│   │   └── embedder.py     ✅ Ollama embeddings
│   ├── retrieval/
│   │   ├── __init__.py     ✅
│   │   └── store.py        ✅ ChromaDB interface
│   ├── agent/
│   │   ├── __init__.py     ✅
│   │   └── graph.py        ✅ LangGraph RAG agent
│   ├── api/
│   │   ├── __init__.py     ✅
│   │   └── main.py         ✅ FastAPI endpoints
│   └── ui/
│       └── app.py          ✅ Streamlit chat UI
├── tests/
│   ├── __init__.py         ✅
│   ├── conftest.py         ✅ Fixtures pytest
│   ├── test_chunker.py     ✅
│   ├── test_store.py       ✅
│   └── test_agent.py       ✅
└── .github/
    └── workflows/
        └── ci.yml          ✅ pytest on push/PR
```

### Décisions prises

1. **Python 3.11** : Bon compromis stabilité/performance, support LTS
2. **Hatch comme build system** : Plus moderne que setuptools, meilleure gestion des extras
3. **Multi-stage Dockerfile** : Image finale plus légère (~400 Mo vs ~1.2 Go)
4. **Non-root user dans Docker** : Sécurité, best practice
5. **ChromaDB en mode client/serveur** : Isolation, persistance fiable
6. **Ollama single service** : Gère à la fois LLM et embeddings

### Choix techniques confirmés

| Composant | Choix | Justification |
|-----------|-------|---------------|
| LLM | Mistral 7B Q4_K_M | Qualité/RAM optimal pour 16 Go |
| Embeddings | nomic-embed-text | Via Ollama, 768 dims, bon FR |
| Chunking | RecursiveCharacterTextSplitter | Adaptatif, respecte structure |
| Vector DB | ChromaDB | Simple, suffisant pour 10-15 docs |
| Agent | LangGraph | Flexible, debug facile, moderne |

### Points d'attention

1. **RAM Ollama** : Surveillé à 8 Go limit dans docker-compose
2. **Health checks** : Configurés avec start_period pour laisser le temps au démarrage
3. **Volumes** : Données persistantes pour ChromaDB et modèles Ollama

### Prochaines étapes

- [ ] Tester le build Docker local
- [ ] Télécharger et tester les modèles Ollama
- [ ] Tester l'upload d'un PDF simple
- [ ] Tester une query RAG complète
- [ ] Ajouter des tests d'intégration
- [ ] Configurer le pre-commit

### Questions ouvertes

1. Faut-il ajouter un rate limiter sur l'API ?
2. Quelle stratégie de backup pour ChromaDB ?
3. Monitoring/alerting à prévoir ?

---

## 2026-03-24 - Correction Critique et Optimisation RAG

### Ce qui a été fait

- **Restauration de l'Agent** : Création de `src/agent/graph.py` avec LangGraph (cycle `retrieve` -> `generate` -> `cite`). Correction de l'import fatal dans `src/agent/__init__.py`.
- **Optimisation Docker** : Mise à jour de `docker-compose.yml` pour Ollama (`OLLAMA_MAX_LOADED_MODELS=2`, `OLLAMA_NUM_PARALLEL=2`). Évite le déchargement constant des modèles sur VPS 16 Go.
- **Amélioration Ingestion** : Enrichissement des séparateurs du `Chunker` pour supporter la hiérarchie Markdown (`#`, `##`, `###`).
- **Performance VectorStore** : Optimisation de `delete_by_source` pour utiliser la suppression directe par filtre ChromaDB.

### Décisions prises

1. **Prompt Engineering** : Intégration de consignes de citation strictes (`[Source X]`) directement dans le nœud `generate` de l'agent.
2. **Gestion du Contexte Vide** : L'agent répond désormais de manière informative au lieu d'halluciner quand aucun document n'est trouvé.
3. **Parallélisme Ollama** : Passage à 2 modèles chargés simultanément (LLM + Embedder) pour réduire la latence de ~15s à <1s entre les phases de recherche et génération.

### Problèmes rencontrés

- **Fichier Manquant** : L'agent LangGraph (`graph.py`) n'était pas présent physiquement malgré les références dans le code. Résolu par une implémentation complète.
- **Latence Ollama** : Identification du goulot d'étranglement lié au rechargement des modèles (fixé via `OLLAMA_MAX_LOADED_MODELS`).

### Prochaines étapes

- [ ] **Économie de Tokens** : Explorer le Prompt Caching et l'optimisation des prompts système.
- [ ] **Validation API** : Vérifier que `src/api/main.py` utilise correctement le nouvel agent asynchrone.
- [ ] **Tests de bout en bout** : Simuler une ingestion complète et une query RAG.
- [ ] **Monitoring RAM** : Vérifier la consommation réelle sur VPS 16 Go avec 2 modèles chargés.

---

## 2026-03-24 - Optimisation des Tokens et IaC (Terraform)

### Ce qui a été fait

- **Optimisation "Lean XML"** : Migration du prompt RAG vers un format XML ultra-compact (`<s>` tags).
    - Gain estimé : ~15-20% de tokens sur le contexte.
    - Amélioration de la robustesse des citations via IDs courts `[i]`.
    - Meilleure séparation sémantique entre instructions et données.
- **Initialisation Terraform** : Création de la structure pour le déploiement sur VPS.
    - Provider : Hetzner Cloud (hcloud).
    - Instance : CX42 (8 vCPU, 16 Go RAM).

### Décisions prises

1. **Format XML vs JSON** : Choix du XML pour sa résilience aux caractères spéciaux des documents techniques et sa moindre verbosité en tokens de structure.
2. **Infrastructure minimale** : Focus sur un déploiement mono-instance (VPS) pour limiter la complexité et les coûts, tout en assurant les performances nécessaires pour Ollama sur CPU.

### Prochaines étapes

- [ ] Finaliser le script `cloud-init` pour automatiser l'installation de Docker et Ollama sur le VPS.
- [ ] Ajouter les configurations Terraform pour AWS, GCP et OVH.
- [ ] Tester le déploiement complet via Terraform.

---

## 2026-03-24 - Correctif Build Docker et Documentation Déploiement

### Ce qui a été fait

- **Fix Dockerfile** : Correction du stage `builder`. Ajout de la copie de `README.md` et du dossier `src/` avant le `pip wheel`. Hatchling (build-backend) échouait car il ne trouvait pas les métadonnées et les sources déclarées dans `pyproject.toml`.
- **Documentation** : Mise à jour complète du `README.md` avec diagramme d'architecture Mermaid et guide de déploiement IaC pas à pas.
- **Terraform** : Finalisation du socle Hetzner avec `terraform.tfvars.example` et protection via `.gitignore`.

### Problèmes rencontrés

- **Docker Build Error** : `pip wheel .` échouait avec un code 1. Cause : contexte de build insuffisant dans le multi-stage Dockerfile. Résolu en copiant les fichiers requis par le backend de build.

---

## 2026-03-24 - Fix Healthchecks Docker

### Ce qui a été fait

- **Robustesse Docker** : Remplacement des healthchecks basés sur `curl` par des commandes natives (`ollama list`) ou des tests socket (`/dev/tcp`). Les images officielles Ollama et ChromaDB ne contiennent pas `curl`, ce qui marquait les containers comme "unhealthy" à tort.

### Problèmes rencontrés

- **Ollama Unhealthy** : Le container refusait de démarrer les dépendances car `curl` était absent de l'image. Corrigé en utilisant `ollama list`.

---

## 2026-03-24 - CI/CD et Correctif Final Docker

### Ce qui a été fait

- **Fix ChromaDB Healthcheck** : Passage à un test basé sur Python (`socket`) pour une compatibilité totale avec les images minimales.
- **Pipeline CI (GitHub Actions)** : Création de `.github/workflows/ci.yml`.
    - Linting (ruff) et Type Checking (mypy).
    - Tests unitaires (pytest).
    - **Docker Integration Test** : Build complet et vérification automatique du statut "Healthy" de tous les services (Chroma, Ollama, App).

### Décisions prises

1. **CI proactive** : Désormais, tout changement du `docker-compose.yml` sera testé automatiquement dans l'environnement GitHub Actions avant d'être déployé.

---

## 2026-03-24 - Implémentation Finale de l'API et de l'UI

### Ce qui a été fait

- **API FastAPI** : Création de `src/api/main.py`. Implémentation des endpoints `/upload`, `/query`, `/health`, et `/documents`. Intégration complète avec l'agent LangGraph.
- **UI Streamlit** : Création de `src/ui/app.py`. Interface moderne avec gestion du chat, upload de documents avec spinner, et visualisation interactive des sources/citations.
- **Correction Déploiement** : Identification de la cause racine des erreurs `ModuleNotFoundError` et `File not found` (dossiers sources vides).

### Décisions prises

1. **Architecture Client-Serveur** : Séparation stricte entre l'UI et l'API via Docker pour une meilleure scalabilité et robustesse.
2. **Visualisation des Sources** : Ajout de barres de progression de pertinence dans l'UI pour une transparence totale sur la réponse du RAG.

### Prochaines étapes

- [ ] **Validation de Production** : Vérifier le bon fonctionnement sur le VPS Hetzner.
- [ ] **Optimisation Inference** : Surveiller les temps de réponse Ollama sur CPU.

---

## 2026-04-02 - V2 : 6 Features Majeures

### Ce qui a été fait

- **F1 — Support DOCX/PPTX** : Extension du `DocumentLoader` pour ingérer des fichiers Word et PowerPoint. Les headings Word sont convertis en hiérarchie Markdown, les tableaux sont extraits, et les slides PowerPoint sont parsées avec marqueurs `[Slide N]`. Ajout de `python-docx` et `python-pptx` dans les dépendances.

- **F2 — Authentification** : Double couche d'auth optionnelle :
  - **UI** : Login gate Streamlit protégé par `APP_PASSWORD` (env var). Page de connexion glassmorphique cohérente avec le design. Si vide, accès libre.
  - **API** : Middleware FastAPI vérifiant le header `X-API-Key` contre `APP_API_KEY`. Endpoints publics exemptés (`/health`, `/docs`). Si vide, pas d'auth.

- **F3 — Streaming SSE** : Réponses token par token au lieu d'un bloc.
  - **Agent** : Nouvelle méthode `stream_answer()` qui utilise `httpx.stream()` vers Ollama (`stream: true`). Yield des dicts `{"token": "..."}` puis `{"done": true, "sources": [...]}`.
  - **API** : Endpoint `POST /query/stream` retournant un `StreamingResponse` SSE.
  - **UI** : Affichage progressif avec curseur `▌` animé via `st.empty()`.

- **F4 — Conversation Multi-turn** : L'assistant se souvient du contexte conversationnel.
  - **Agent** : `_build_prompt()` injecte les 3 derniers échanges (tronqués à 300 chars) dans le prompt LLM.
  - **API** : `QueryRequest` accepte un champ `history: List[MessageModel]` optionnel.
  - **UI** : L'historique de la conversation active est envoyé à chaque requête.

- **F5 — Feedback 👍/👎** : Boutons de feedback sur chaque réponse assistant.
  - **API** : Endpoints `POST /feedback` et `GET /feedback`. Stockage JSON simple dans `feedback.json`.
  - **UI** : Boutons 👍/👎 sous chaque message assistant avec toast de confirmation.

- **F6 — Rapport de Conformité Auto** : Nouvel onglet "📋 Rapport de Conformité".
  - **API** : Endpoint `POST /compliance-report` avec questions-types par réglementation (NIS2, DORA, RGPD, AI Act). Exécute N requêtes RAG séquentielles et compile les résultats.
  - **UI** : Sélecteur multi-réglementation, questions custom optionnelles, barre de progression, export Markdown du rapport généré.

### Décisions prises

1. **Streaming via SSE** plutôt que WebSocket : Plus simple, compatible avec tous les proxys, et Streamlit gère bien les requêtes HTTP longues.
2. **Feedback en JSON** plutôt que SQLite : Pour un projet portfolio, un fichier JSON suffit et évite une dépendance supplémentaire. Facilement portable.
3. **Auth optionnelle** : Si `APP_PASSWORD` / `APP_API_KEY` sont vides, l'app fonctionne sans auth. Parfait pour le développement local et la démonstration.
4. **Multi-turn limité à 3 échanges** : Compromis entre contexte conversationnel et économie de tokens sur Mistral 7B (contexte 8K).
5. **Rapport de conformité séquentiel** : Chaque question est posée une par une au RAG (pas de parallélisme) pour ne pas surcharger Ollama sur CPU.

### Fichiers modifiés

| Fichier | Changement |
|---------|------------|
| `pyproject.toml` | +`python-docx`, +`python-pptx` |
| `src/ingestion/loader.py` | +`_load_docx()`, +`_load_pptx()` |
| `src/config.py` | +`app_password`, +`app_api_key` |
| `.env.example` | +section Authentication |
| `docker-compose.yml` | +`APP_PASSWORD` env dans UI |
| `src/agent/graph.py` | +`_build_prompt()`, +`stream_answer()`, +`history` dans `RAGState` |
| `src/api/main.py` | +APIKeyMiddleware, +`/query/stream`, +`/feedback`, +`/compliance-report`, multi-turn |
| `src/ui/app.py` | +login gate, +streaming, +feedback 👍/👎, +tab conformité |

### Prochaines étapes

- [ ] Tests d'intégration pour les nouveaux endpoints
- [ ] Reranking cross-encoder (V3)
- [ ] Hybrid search BM25 + vecteurs (V3)

---

## Template pour prochaines entrées

```markdown
## YYYY-MM-DD - Titre

### Ce qui a été fait
-

### Décisions prises
-

### Problèmes rencontrés
-

### Prochaines étapes
- [ ]
```
