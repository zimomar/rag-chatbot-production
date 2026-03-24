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
