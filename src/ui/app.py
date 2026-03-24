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

# Configuration de l'URL API (par défaut via docker ou local)
API_URL = os.getenv("API_URL", "http://api:8000")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Sidebar: Ingestion & Stats ---
with st.sidebar:
    st.title("🤖 RAG Local")
    st.markdown("---")
    
    # Upload de documents
    st.subheader("📁 Ingestion")
    uploaded_file = st.file_uploader(
        "Uploader un document (PDF, MD)", 
        type=["pdf", "md", "markdown"]
    )
    
    if uploaded_file is not None:
        if st.button("Indexer le document", use_container_width=True):
            with st.spinner("Indexation en cours..."):
                try:
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                    response = httpx.post(f"{API_URL}/upload", files=files, timeout=60)
                    if response.status_code == 200:
                        st.success(f"Document indexé : {uploaded_file.name}")
                        st.rerun()
                    else:
                        st.error(f"Erreur d'indexation: {response.text}")
                except Exception as e:
                    st.error(f"Impossible de contacter l'API: {e}")

    st.markdown("---")
    
    # Liste des documents
    st.subheader("📚 Documents Indexés")
    try:
        docs_res = httpx.get(f"{API_URL}/documents")
        if docs_res.status_code == 200:
            indexed_docs = docs_res.json().get("documents", [])
            if not indexed_docs:
                st.info("Aucun document indexé pour le moment.")
            for doc_name in indexed_docs:
                col1, col2 = st.columns([0.8, 0.2])
                col1.text(f"📄 {doc_name}")
                if col2.button("🗑️", key=doc_name):
                    httpx.delete(f"{API_URL}/documents/{doc_name}")
                    st.rerun()
        else:
            st.warning("Erreur lors de la récupération des documents.")
    except Exception:
        st.error("L'API n'est pas accessible.")

# --- Main UI: Chat ---
st.title("Conversation Documentaire")
st.caption("Posez des questions à vos documents indexés. Réponses 100% locales.")

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
