"""
Interface utilisateur Streamlit pour le Chatbot RAG Local.
"""

import os
import streamlit as st
import httpx
import logging

# Configuration de la page
st.set_page_config(
    page_title="RAG Local Chatbot",
    page_icon="🤖",
    layout="wide",
)

# --- Custom CSS for Modern Light Glassy Look ---
st.markdown("""
    <style>
    /* Fond principal total */
    .stApp, .stAppViewContainer, .stMain, .stAppHeader {
        background: #f8fafc !important;
        background-color: #f8fafc !important;
    }

    /* Sidebar : Forcer le fond clair */
    [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {
        background-color: #ffffff !important;
        background: #ffffff !important;
        border-right: 1px solid #e2e8f0 !important;
    }

    /* Bulles de Chat */
    [data-testid="stChatMessage"] {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 15px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
        color: #1e293b !important;
    }

    /* Message Utilisateur (teinte bleue très légère) */
    [data-testid="stChatMessage"]:has(div[data-testid="user-avatar"]) {
        background-color: #f0f7ff !important;
    }

    /* ZONE DE SAISIE (FOOTER) : Forcer le fond blanc total */
    div[data-testid="stBottom"] {
        background-color: #f8fafc !important;
    }
    
    div[data-testid="stBottom"] > div {
        background-color: transparent !important;
    }

    [data-testid="stChatInput"] {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 12px !important;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05) !important;
    }

    /* Forcer la couleur du texte et du curseur dans le champ */
    [data-testid="stChatInput"] textarea {
        color: #1e293b !important;
        background-color: #ffffff !important;
    }

    /* Style du bouton d'envoi (flèche) */
    [data-testid="stChatInput"] button {
        background-color: #f8fafc !important;
        color: #3b82f6 !important;
    }

    /* FILE UPLOADER : Forcer le style clair */
    [data-testid="stFileUploader"] {
        background-color: #f1f5f9 !important;
        border: 2px dashed #cbd5e1 !important;
        border-radius: 10px !important;
        padding: 10px !important;
    }
    [data-testid="stFileUploader"] section {
        background-color: transparent !important;
    }
    /* Ciblage spécifique du bouton "Browse files" */
    [data-testid="stFileUploader"] button {
        background-color: #ffffff !important;
        color: #1e293b !important;
        border: 1px solid #e2e8f0 !important;
    }
    [data-testid="stFileUploader"] button:hover {
        background-color: #eff6ff !important;
        border-color: #3b82f6 !important;
        color: #3b82f6 !important;
    }
    [data-testid="stFileUploader"] label {
        color: #475569 !important;
    }

    }

    /* Textes et Titres */
    h1, h2, h3, p, span, label, div {
        color: #1e293b !important;
    }
    
    h1 {
        font-weight: 800 !important;
        background: linear-gradient(90deg, #1e293b, #3b82f6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    /* Cacher les éléments superflus */
    #MainMenu, footer, header {
        visibility: hidden;
    }
    </style>
    """, unsafe_allow_html=True)

# Configuration de l'URL API (par défaut via docker ou local)
API_URL = os.getenv("API_URL", "http://api:8000")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Sidebar: Ingestion & Stats ---
with st.sidebar:
    st.title("🤖 RAG Local")
    st.markdown("---")
    
    # Upload de documents avec indexation automatique
    st.subheader("📁 Ingestion")
    uploaded_files = st.file_uploader(
        "Glissez vos documents ici (PDF, MD)", 
        type=["pdf", "md", "markdown"],
        accept_multiple_files=True
    )
    
    # Logique d'indexation automatique
    if uploaded_files:
        if "processed_files" not in st.session_state:
            st.session_state.processed_files = set()
            
        for uploaded_file in uploaded_files:
            # On n'indexe que si le fichier n'a pas encore été traité dans cette session
            if uploaded_file.name not in st.session_state.processed_files:
                with st.status(f"Indexation de {uploaded_file.name}...") as status:
                    try:
                        files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                        response = httpx.post(f"{API_URL}/upload", files=files, timeout=60)
                        if response.status_code == 200:
                            st.session_state.processed_files.add(uploaded_file.name)
                            status.update(label=f"✅ {uploaded_file.name} indexé !", state="complete")
                        else:
                            status.update(label=f"❌ Erreur sur {uploaded_file.name}", state="error")
                            st.error(f"Détail: {response.text}")
                    except Exception as e:
                        status.update(label="❌ Erreur de connexion", state="error")
                        st.error(f"Impossible de contacter l'API: {e}")
        
        # Petit bouton pour rafraîchir la liste si besoin (optionnel car st.status aide déjà)
        if st.button("Actualiser la bibliothèque", use_container_width=True):
            st.rerun()

    st.markdown("---")
    
    # Liste des documents
    st.subheader("📚 Bibliothèque")
    try:
        docs_res = httpx.get(f"{API_URL}/documents")
        if docs_res.status_code == 200:
            indexed_docs = docs_res.json().get("documents", [])
            if not indexed_docs:
                st.info("Aucun document indexé.")
            for doc_name in indexed_docs:
                col1, col2 = st.columns([0.85, 0.15])
                col1.markdown(f"**📄 {doc_name}**")
                if col2.button("🗑️", key=f"del_{doc_name}"):
                    httpx.delete(f"{API_URL}/documents/{doc_name}")
                    if doc_name in st.session_state.get("processed_files", set()):
                        st.session_state.processed_files.remove(doc_name)
                    st.rerun()
        else:
            st.warning("Erreur API Documents.")
    except Exception:
        st.error("L'API n'est pas accessible.")

# --- Main UI: Chat ---
st.title("Conversation")
st.caption("Intelligence locale basée sur vos documents")

# Historique du chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# Affichage des messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        # Affichage des sources si présentes
        if "sources" in message and message["sources"]:
            with st.expander("Sources consultées"):
                for src in message["sources"]:
                    st.markdown(f"**{src['document']}** (Page {src['page'] or 'N/A'})")
                    st.caption(f"_{src['excerpt']}_")
                    st.progress(src['relevance_score'], text=f"Pertinence: {int(src['relevance_score']*100)}%")

# Entrée utilisateur
if prompt := st.chat_input("Que voulez-vous savoir ?"):
    # Ajout du message utilisateur
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Appel à l'API de l'agent
    with st.chat_message("assistant"):
        with st.spinner("Recherche et génération..."):
            try:
                response = httpx.post(
                    f"{API_URL}/query", 
                    json={"question": prompt}, 
                    timeout=120
                )
                if response.status_code == 200:
                    data = response.json()
                    answer = data["answer"]
                    sources = data["sources"]
                    confidence = data["confidence"]
                    
                    st.markdown(answer)
                    if confidence > 0:
                        st.caption(f"Score de confiance: {int(confidence*100)}%")

                    # Affichage des sources dans l'expander
                    if sources:
                        with st.expander("Sources consultées"):
                            for src in sources:
                                st.markdown(f"**{src['document']}** (Page {src['page'] or 'N/A'})")
                                st.caption(f"_{src['excerpt']}_")
                                st.progress(src['relevance_score'], text=f"Pertinence: {int(src['relevance_score']*100)}%")

                    # Enregistrement du message assistant
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": answer,
                        "sources": sources
                    })
                else:
                    error_msg = f"Erreur de l'agent: {response.text}"
                    st.error(error_msg)
            except Exception as e:
                error_msg = f"Impossible de contacter l'agent RAG : {e}"
                st.error(error_msg)
                logger.error(error_msg)
