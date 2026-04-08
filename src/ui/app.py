"""
Interface utilisateur Streamlit pour le Chatbot RAG Local.
Design glassmorphique premium avec mode clair/sombre,
historique de conversations et analyse d'infrastructure.
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime

import httpx
import streamlit as st

# Configuration de la page
st.set_page_config(
    page_title="RAG Local Chatbot",
    page_icon="🤖",
    layout="wide",
)

# --- Theme State ---
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

is_dark = st.session_state.dark_mode

# --- Shared CSS (animations, layout, fonts — theme-independent) ---
SHARED_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0&display=swap');

    :root {
        --primary: #6366f1;
        --primary-hover: #4f46e5;
        --sidebar-width: 320px;
    }

    @keyframes slideUpFade {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes pulseSoft {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }

    .stApp {
        font-family: 'Inter', -apple-system, sans-serif !important;
    }

    #MainMenu, footer { visibility: hidden; }

    .hero-section {
        padding: 4rem 1rem;
        animation: slideUpFade 0.8s cubic-bezier(0.2, 0.8, 0.2, 1);
        text-align: center;
    }
    .hero-section h1 {
        font-size: 3.5rem !important;
        margin-bottom: 1rem !important;
        font-weight: 800 !important;
    }
    .hero-subtitle {
        font-size: 1.2rem !important;
        opacity: 0.8;
        max-width: 600px;
        margin: 0 auto !important;
    }

    .welcome-card {
        padding: 2rem;
        text-align: center;
        cursor: pointer;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 1rem;
        height: 100%;
    }
    .welcome-card .emoji {
        font-size: 2.5rem;
        background: linear-gradient(135deg, var(--primary), #06b6d4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    .welcome-card .card-title {
        font-size: 1.1rem;
        font-weight: 700;
    }
    .welcome-card .card-desc {
        font-size: 0.9rem;
        line-height: 1.5;
        opacity: 0.7;
    }

    [data-testid="stChatMessage"] {
        animation: slideUpFade 0.5s cubic-bezier(0.2, 0.8, 0.2, 1);
    }

    .confidence-badge {
        font-family: 'JetBrains Mono', monospace;
        font-weight: 500;
        letter-spacing: -0.01em;
        text-transform: uppercase;
    }

    /* Customizing Tabs */
    .stTabs [data-baseweb="tab-list"] {
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        padding-bottom: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 45px !important;
        padding: 0 24px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        border: none !important;
        transition: all 0.2s ease !important;
    }
    .stTabs [aria-selected="true"] {
        color: var(--primary) !important;
    }

    @keyframes typingPulse {
        0%, 60%, 100% { opacity: 0.3; transform: scale(0.8); }
        30% { opacity: 1; transform: scale(1.1); }
    }
    .typing-indicator {
        display: flex; align-items: center; gap: 6px; padding: 1rem;
        background: rgba(255, 255, 255, 0.03);
        border-radius: 16px; width: fit-content;
    }
    .typing-indicator .dot {
        width: 8px; height: 8px; border-radius: 50%; background: var(--primary);
        animation: typingPulse 1.4s ease-in-out infinite;
    }
    .typing-indicator .dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-indicator .dot:nth-child(3) { animation-delay: 0.4s; }

    .dashboard-card {
        background: rgba(30, 41, 59, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 20px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        backdrop-filter: blur(12px);
    }
    .status-pill {
        display: inline-flex;
        align-items: center;
        padding: 2px 12px;
        border-radius: 99px;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
    }
    .status-high { background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.2); }
    .status-med { background: rgba(249, 115, 22, 0.1); color: #f97316; border: 1px solid rgba(249, 115, 22, 0.2); }
    .status-low { background: rgba(34, 197, 94, 0.1); color: #22c55e; border: 1px solid rgba(34, 197, 94, 0.2); }

    /* Scrollbar refinement */
    ::-webkit-scrollbar { width: 4px; height: 4px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
        background: rgba(99, 102, 241, 0.2);
        border-radius: 10px;
    }
    ::-webkit-scrollbar-thumb:hover { background: rgba(99, 102, 241, 0.4); }

    /* Button adjustments */
    .stButton button {
        border-radius: 12px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.5rem !important;
    }
</style>
"""

# --- Dark Theme CSS ---
DARK_CSS = """
<style>
    .stApp, .stAppViewContainer, .stMain {
        background: radial-gradient(circle at top left, #1e1b4b, #0f172a 40%),
                    radial-gradient(circle at bottom right, #1e293b, #0f172a 40%) !important;
        background-attachment: fixed !important;
    }
    .stAppHeader {
        background: rgba(15, 23, 42, 0.7) !important;
        backdrop-filter: blur(24px) saturate(180%) !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
    }

    [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {
        background: rgba(15, 23, 42, 0.8) !important;
        backdrop-filter: blur(32px) saturate(200%) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
    }
    [data-testid="stSidebar"] * { color: #94a3b8 !important; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #f8fafc !important; -webkit-text-fill-color: #f8fafc !important; background: none !important;
    }

    [data-testid="stSidebar"] .stButton > button {
        background: rgba(99, 102, 241, 0.08) !important;
        border: 1px solid rgba(99, 102, 241, 0.15) !important;
        color: #c7d2fe !important; border-radius: 12px !important;
        backdrop-filter: blur(12px) !important; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        font-weight: 500 !important; font-size: 0.85rem !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(99, 102, 241, 0.15) !important;
        border-color: rgba(99, 102, 241, 0.3) !important;
        box-shadow: 0 4px 20px rgba(99, 102, 241, 0.15) !important;
        transform: translateY(-2px) !important;
    }

    [data-testid="stChatMessage"] {
        background: rgba(30, 41, 59, 0.4) !important;
        backdrop-filter: blur(24px) saturate(150%) !important;
        border: 1px solid rgba(255, 255, 255, 0.04) !important;
        border-radius: 24px !important;
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.3) !important;
        padding: 1.5rem !important;
        margin-bottom: 1.5rem !important;
        max-width: 90%;
    }
    [data-testid="stChatMessage"]:has(div[data-testid="user-avatar"]) {
        background: rgba(99, 102, 241, 0.1) !important;
        border-color: rgba(99, 102, 241, 0.2) !important;
        margin-left: auto !important;
    }
    [data-testid="stChatMessage"] div[data-testid="stChatMessageContent"] {
        padding-top: 0.5rem;
    }

    .source-container {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        margin-top: 1rem;
        padding-top: 1rem;
        border-top: 1px solid rgba(255, 255, 255, 0.05);
    }
    .source-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 12px;
        padding: 0.75rem 1rem;
        font-size: 0.85rem;
        transition: all 0.2s ease;
        flex: 1 1 200px;
    }
    .source-card:hover {
        background: rgba(255, 255, 255, 0.05);
        border-color: rgba(99, 102, 241, 0.3);
    }
    .source-tag {
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        padding: 2px 6px;
        border-radius: 4px;
        background: rgba(99, 102, 241, 0.2);
        color: #818cf8;
        margin-right: 6px;
    }
    [data-testid="stChatMessage"] * { color: #cbd5e1 !important; }

    div[data-testid="stBottom"] {
        background: transparent !important;
    }
    div[data-testid="stBottom"] > div { background: transparent !important; }
    [data-testid="stChatInput"] {
        background: rgba(30, 41, 59, 0.6) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 20px !important;
        backdrop-filter: blur(24px) !important;
        box-shadow: 0 20px 50px -12px rgba(0, 0, 0, 0.5) !important;
        padding: 4px !important;
    }
    [data-testid="stChatInput"] textarea { color: #f8fafc !important; }
    [data-testid="stChatInput"] button {
        background: #6366f1 !important;
        border-radius: 14px !important;
        transition: all 0.3s ease !important;
    }

    [data-testid="stExpander"] {
        background: rgba(15, 23, 42, 0.3) !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-radius: 16px !important;
    }
    [data-testid="stExpander"] summary { color: #818cf8 !important; }

    .main h1 {
        font-weight: 800 !important;
        letter-spacing: -0.025em !important;
        background: linear-gradient(135deg, #f8fafc 0%, #818cf8 50%, #6366f1 100%) !important;
        -webkit-background-clip: text !important; -webkit-text-fill-color: transparent !important;
    }

    .welcome-card {
        background: rgba(30, 41, 59, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 24px;
        backdrop-filter: blur(16px);
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    }
    .welcome-card:hover {
        background: rgba(99, 102, 241, 0.1);
        border-color: rgba(99, 102, 241, 0.2);
        transform: translateY(-8px) scale(1.02);
        box-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.3);
    }
</style>
"""

# --- Light Theme CSS ---
LIGHT_CSS = """
<style>
    .stApp, .stAppViewContainer, .stMain {
        background: radial-gradient(circle at top left, #f5f3ff, #f8fafc 40%),
                    radial-gradient(circle at bottom right, #e0e7ff, #f8fafc 40%) !important;
        background-attachment: fixed !important;
    }
    .stAppHeader {
        background: rgba(255, 255, 255, 0.7) !important;
        backdrop-filter: blur(24px) saturate(180%) !important;
        border-bottom: 1px solid rgba(0, 0, 0, 0.05) !important;
    }

    [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {
        background: rgba(255, 255, 255, 0.8) !important;
        backdrop-filter: blur(32px) saturate(200%) !important;
        border-right: 1px solid rgba(0, 0, 0, 0.05) !important;
    }
    [data-testid="stSidebar"] * { color: #475569 !important; }

    [data-testid="stChatMessage"] {
        background: rgba(255, 255, 255, 0.6) !important;
        backdrop-filter: blur(24px) saturate(150%) !important;
        border: 1px solid rgba(0, 0, 0, 0.04) !important;
        border-radius: 20px !important;
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.05) !important;
        padding: 1.5rem !important; margin-bottom: 1.5rem !important;
    }
    [data-testid="stChatMessage"]:has(div[data-testid="user-avatar"]) {
        background: rgba(99, 102, 241, 0.04) !important;
        border-color: rgba(99, 102, 241, 0.08) !important;
    }

    [data-testid="stChatInput"] {
        background: rgba(255, 255, 255, 0.8) !important;
        border: 1px solid rgba(0, 0, 0, 0.08) !important;
        border-radius: 20px !important;
        backdrop-filter: blur(24px) !important;
        box-shadow: 0 20px 50px -12px rgba(0, 0, 0, 0.1) !important;
    }

    .main h1 {
        background: linear-gradient(135deg, #1e293b 0%, #4f46e5 50%, #6366f1 100%) !important;
        -webkit-background-clip: text !important; -webkit-text-fill-color: transparent !important;
    }

    .welcome-card {
        background: rgba(255, 255, 255, 0.6);
        border: 1px solid rgba(0, 0, 0, 0.05);
        border-radius: 24px;
        backdrop-filter: blur(16px);
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    }
    .welcome-card:hover {
        background: rgba(255, 255, 255, 0.9);
        border-color: rgba(99, 102, 241, 0.2);
        transform: translateY(-8px) scale(1.02);
        box-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.08);
    }
</style>
"""

# Inject CSS
st.markdown(SHARED_CSS, unsafe_allow_html=True)
st.markdown(DARK_CSS if is_dark else LIGHT_CSS, unsafe_allow_html=True)

# Initialisation de l'API et configurations locales
API_URL = os.getenv("API_URL", "http://api:8000")


def format_audit_report(text: str) -> str:
    """Parse permissivement le texte Markdown pour injecter des badges HTML de priorité et des cartes."""
    try:
        parts = text.split("### ")
        if len(parts) <= 1:
            return f'<div class="dashboard-card">{text}</div>'

        formatted_report = parts[0]

        for part in parts[1:]:
            lines = part.split("\n", 1)
            title = lines[0]
            body = lines[1] if len(lines) > 1 else ""

            # Recherche permissive de priorité
            priority_match = re.search(
                r"(?i)[-*]?\s*\**priorit[eé]\**\s*:\s*\**([a-zA-Z\s]+)", body
            )
            badge_html = ""
            pill_class = "status-low"
            if priority_match:
                p_val = priority_match.group(1).lower().replace("*", "").strip()
                if p_val.startswith("haute"):
                    pill_class = "status-high"
                elif p_val.startswith("moyenne"):
                    pill_class = "status-med"
                
                badge_html = f'<span class="status-pill {pill_class}">{p_val.upper()}</span>'

            formatted_report += f"""
            <div class="dashboard-card">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem;">
                    <h4 style="margin: 0; font-size: 1.1rem; color: #f8fafc;">{title}</h4>
                    {badge_html}
                </div>
                <div style="font-size: 0.95rem; line-height: 1.6; color: #cbd5e1;">
                    {body}
                </div>
            </div>
            """

        return formatted_report
    except Exception as e:
        logger.warning(f"Erreur lors du formatage HTML du rapport: {e}")
        return text


def render_sources(sources):
    """Rendu élégant des sources sous forme de cartes HTML."""
    if not sources:
        return
    
    source_html = '<div class="source-container">'
    for src in sources:
        doc_name = src.get("document", "Document inconnu")
        page = src.get("page", "N/A")
        score = int(src.get("relevance_score", 0) * 100)
        excerpt = src.get("excerpt", "")
        
        source_html += f"""
        <div class="source-card">
            <div style="margin-bottom: 0.5rem;">
                <span class="source-tag">DOC</span>
                <span style="font-weight: 600; color: #f8fafc;">{doc_name}</span>
            </div>
            <div style="font-size: 0.75rem; opacity: 0.8; margin-bottom: 0.5rem;">
                Page {page} • Pertinence {score}%
            </div>
            <div style="font-style: italic; font-size: 0.75rem; opacity: 0.6; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                "{excerpt}"
            </div>
        </div>
        """
    source_html += "</div>"
    st.markdown(source_html, unsafe_allow_html=True)


APP_PASSWORD = os.getenv("APP_PASSWORD", "")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =====================================================================
# AUTHENTICATION GATE
# =====================================================================
def check_auth():
    """Vérifie l'authentification si APP_PASSWORD est configuré."""
    if not APP_PASSWORD:
        return True

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    # Login page
    st.markdown(
        """
    <div class="hero-section">
        <h1>🔒 RAG Local</h1>
        <p class="hero-subtitle">Authentification requise pour accéder à l'application</p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        with st.form("login_form"):
            password = st.text_input(
                "Mot de passe", type="password", placeholder="Entrez le mot de passe"
            )
            submitted = st.form_submit_button(
                ":material/lock_open: Se connecter", use_container_width=True, type="primary"
            )
            if submitted:
                if password == APP_PASSWORD:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("❌ Mot de passe incorrect")
    return False


if not check_auth():
    st.stop()


# =====================================================================
# SESSION STATE INITIALIZATION
# =====================================================================
def init_session_state():
    """Initialise l'état de session avec les valeurs par défaut."""
    if "conversations" not in st.session_state:
        first_id = str(uuid.uuid4())
        st.session_state.conversations = {
            first_id: {
                "id": first_id,
                "title": "Nouvelle conversation",
                "messages": [],
                "created_at": datetime.now().isoformat(),
            }
        }
        st.session_state.active_conversation_id = first_id

    if "active_conversation_id" not in st.session_state:
        st.session_state.active_conversation_id = list(st.session_state.conversations.keys())[0]

    if "processed_files" not in st.session_state:
        st.session_state.processed_files = set()


init_session_state()


def get_active_conversation():
    """Retourne la conversation active."""
    cid = st.session_state.active_conversation_id
    return st.session_state.conversations.get(cid, None)


def create_new_conversation():
    """Crée une nouvelle conversation et la rend active."""
    new_id = str(uuid.uuid4())
    st.session_state.conversations[new_id] = {
        "id": new_id,
        "title": "Nouvelle conversation",
        "messages": [],
        "created_at": datetime.now().isoformat(),
    }
    st.session_state.active_conversation_id = new_id


def switch_conversation(conv_id: str):
    """Change la conversation active."""
    st.session_state.active_conversation_id = conv_id


def delete_conversation(conv_id: str):
    """Supprime une conversation. S'il n'en reste qu'une, en crée une nouvelle."""
    if conv_id in st.session_state.conversations:
        del st.session_state.conversations[conv_id]
    if not st.session_state.conversations:
        create_new_conversation()
    elif conv_id == st.session_state.active_conversation_id:
        st.session_state.active_conversation_id = list(st.session_state.conversations.keys())[0]


def export_conversation_md(conv):
    """Exporte une conversation en Markdown."""
    lines = [f"# {conv['title']}\n", f"*{conv['created_at']}*\n\n---\n"]
    for msg in conv["messages"]:
        role = "🧑 Utilisateur" if msg["role"] == "user" else "🤖 Assistant"
        lines.append(f"### {role}\n\n{msg['content']}\n\n")
    return "\n".join(lines)


# =====================================================================
# SIDEBAR
# =====================================================================
with st.sidebar:
    st.markdown("## :material/smart_toy: RAG Local")
    st.caption("Intelligence documentaire locale")

    # --- Theme Toggle ---
    theme_label = (
        ":material/dark_mode: Mode sombre" if is_dark else ":material/light_mode: Mode clair"
    )
    if st.toggle(theme_label, value=is_dark, key="theme_toggle"):
        if not st.session_state.dark_mode:
            st.session_state.dark_mode = True
            st.rerun()
    else:
        if st.session_state.dark_mode:
            st.session_state.dark_mode = False
            st.rerun()

    st.markdown("---")

    # --- Chat History ---
    st.markdown("### :material/forum: Conversations")
    if st.button(":material/add: Nouvelle conversation", use_container_width=True):
        create_new_conversation()
        st.rerun()

    # List conversations (newest first)
    sorted_convs = sorted(
        st.session_state.conversations.values(),
        key=lambda c: c["created_at"],
        reverse=True,
    )
    for conv in sorted_convs:
        is_active = conv["id"] == st.session_state.active_conversation_id
        col1, col2 = st.columns([0.85, 0.15])
        with col1:
            label = f"{'▶ ' if is_active else ''}{conv['title']}"
            if st.button(
                label,
                key=f"conv_{conv['id']}",
                use_container_width=True,
            ):
                switch_conversation(conv["id"])
                st.rerun()
        with col2:
            if st.button(":material/delete:", key=f"del_conv_{conv['id']}"):
                delete_conversation(conv["id"])
                st.rerun()

    st.markdown("---")

    # --- Document Ingestion ---
    st.markdown("### 📁 Ingestion")
    uploaded_files = st.file_uploader(
        "Glissez vos documents ici",
        type=["pdf", "md", "markdown", "docx", "pptx"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        for uploaded_file in uploaded_files:
            if uploaded_file.name not in st.session_state.processed_files:
                with st.status(f"Indexation de {uploaded_file.name}...") as status:
                    try:
                        files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                        response = httpx.post(f"{API_URL}/upload", files=files, timeout=60)
                        if response.status_code == 200:
                            st.session_state.processed_files.add(uploaded_file.name)
                            status.update(
                                label=f"✅ {uploaded_file.name} indexé !",
                                state="complete",
                            )
                        else:
                            status.update(
                                label=f":material/error: Erreur sur {uploaded_file.name}",
                                state="error",
                            )
                            st.error(f"Détail: {response.text}")
                    except Exception as e:
                        status.update(label=":material/error: Erreur de connexion", state="error")
                        st.error(f"Impossible de contacter l'API: {e}")

        if st.button("Actualiser la bibliothèque", use_container_width=True):
            st.rerun()

    st.markdown("---")

    # --- Document Library ---
    st.markdown("### :material/library_books: Bibliothèque")
    try:
        docs_res = httpx.get(f"{API_URL}/documents")
        if docs_res.status_code == 200:
            indexed_docs = docs_res.json().get("documents", [])
            if not indexed_docs:
                st.info("Aucun document indexé.")
            for doc_name in indexed_docs:
                col1, col2 = st.columns([0.85, 0.15])
                col1.markdown(f"📄 **{doc_name}**")
                if col2.button(":material/delete:", key=f"del_{doc_name}"):
                    httpx.delete(f"{API_URL}/documents/{doc_name}")
                    if doc_name in st.session_state.processed_files:
                        st.session_state.processed_files.remove(doc_name)
                    st.rerun()
        else:
            st.warning("Erreur API Documents.")
    except Exception:
        st.error("L'API n'est pas accessible.")


# =====================================================================
# MAIN CONTENT AREA — TABS
# =====================================================================
tab_chat, tab_infra, tab_compliance = st.tabs(
    [
        ":material/chat: Conversation",
        ":material/architecture: Analyse d'Infrastructure",
        ":material/policy: Rapport de Conformité",
    ]
)


# =====================================================================
# TAB 1: CHAT
# =====================================================================
with tab_chat:
    if "is_generating" not in st.session_state:
        st.session_state.is_generating = False

    conv = get_active_conversation()
    if not conv:
        st.error("Aucune conversation sélectionnée.")
        st.stop()

    # --- Welcome Screen (when no messages) ---
    if not conv["messages"]:
        st.markdown(
            """
        <div class="hero-section">
            <h1>🤖 RAG Local</h1>
            <p class="hero-subtitle">Intelligence locale basée sur vos documents</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

        # Suggested prompts
        cols = st.columns(3)
        suggestions = [
            ("summarize", "Résumer un document", "Fais un résumé du dernier document indexé"),
            (
                "search",
                "Recherche précise",
                "Quelles sont les obligations de conformité décrites dans mes documents ?",
            ),
            (
                "gavel",
                "Réglementation EU",
                "Quels articles du RGPD s'appliquent au traitement de données de mes clients ?",
            ),
        ]
        for col, (emoji, title, prompt_text) in zip(cols, suggestions, strict=False):
            with col:
                st.markdown(
                    f"""
                <div class="welcome-card">
                    <div class="emoji"><span class="material-symbols-rounded" style="font-size: 3.5rem;">{emoji}</span></div>
                    <div class="card-title">{title}</div>
                    <div class="card-desc">{prompt_text[:60]}...</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
                if st.button(title, key=f"sug_{title}", use_container_width=True):
                    conv["messages"].append({"role": "user", "content": prompt_text})
                    conv["title"] = prompt_text[:40]
                    st.rerun()
    else:
        # --- Title & Export ---
        col_title, col_export = st.columns([0.9, 0.1])
        with col_title:
            st.markdown(f"## {conv['title']}")
        with col_export:
            md_export = export_conversation_md(conv)
            st.download_button(
                ":material/download:",
                data=md_export,
                file_name=f"conversation_{conv['id'][:8]}.md",
                mime="text/markdown",
                help="Exporter en Markdown",
            )

    # --- Display Messages ---
    for msg_idx, message in enumerate(conv["messages"]):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            render_sources(message.get("sources", []))
            if "confidence" in message and message["confidence"] > 0:
                st.markdown(
                    f'<span class="confidence-badge">🧠 Confiance: {int(message["confidence"] * 100)}%</span>',
                    unsafe_allow_html=True,
                )
            # --- Feedback buttons (assistant messages only) ---
            if message["role"] == "assistant":
                feedback_key = f"fb_{conv['id']}_{msg_idx}"
                col_fb1, col_fb2, col_fb_space = st.columns([0.08, 0.08, 0.84])
                with col_fb1:
                    if st.button(
                        ":material/thumb_up:", key=f"{feedback_key}_up", help="Bonne réponse"
                    ):
                        try:
                            # Find the user question for this answer
                            user_q = conv["messages"][msg_idx - 1]["content"] if msg_idx > 0 else ""
                            httpx.post(
                                f"{API_URL}/feedback",
                                json={
                                    "question": user_q,
                                    "answer": message["content"][:500],
                                    "rating": 1,
                                },
                                timeout=5,
                            )
                            st.toast("✅ Merci pour votre feedback !", icon=":material/thumb_up:")
                        except Exception:
                            pass
                with col_fb2:
                    if st.button(
                        ":material/thumb_down:", key=f"{feedback_key}_down", help="Mauvaise réponse"
                    ):
                        try:
                            user_q = conv["messages"][msg_idx - 1]["content"] if msg_idx > 0 else ""
                            httpx.post(
                                f"{API_URL}/feedback",
                                json={
                                    "question": user_q,
                                    "answer": message["content"][:500],
                                    "rating": 0,
                                },
                                timeout=5,
                            )
                            st.toast(
                                "📝 Merci, nous allons améliorer nos réponses.",
                                icon=":material/thumb_down:",
                            )
                        except Exception:
                            pass

    stream_placeholder = st.container()

    # --- Chat Input (Streaming + Multi-turn) ---
    disabled = st.session_state.get("is_generating", False)
    prompt = st.chat_input("Que voulez-vous savoir ?", disabled=disabled)

    if prompt:
        if not conv["messages"]:
            conv["title"] = prompt[:40] + ("..." if len(prompt) > 40 else "")

        conv["messages"].append({"role": "user", "content": prompt})
        st.session_state.is_generating = True
        st.rerun()

    if st.session_state.get("is_generating", False):
        # Build multi-turn history
        history_payload = [
            {"role": m["role"], "content": m["content"]}
            for m in conv["messages"][:-1]  # exclude current prompt
            if m["role"] in ("user", "assistant")
        ]

        with stream_placeholder:
            with st.chat_message("assistant"):
                response_placeholder = st.empty()
                full_response = ""
                sources = []
                confidence = 0.0

                try:
                    # Streaming SSE request
                    with httpx.stream(
                        "POST",
                        f"{API_URL}/query/stream",
                        json={
                            "question": conv["messages"][-1]["content"],
                            "history": history_payload or None,
                        },
                        timeout=600,
                    ) as stream_response:
                        if stream_response.status_code != 200:
                            st.error(f"Erreur de l'agent: {stream_response.status_code}")
                        else:
                            for line in stream_response.iter_lines():
                                if line.startswith("data: "):
                                    try:
                                        data = json.loads(line[6:])
                                        if "token" in data:
                                            full_response += data["token"]
                                            response_placeholder.markdown(full_response + "▌")
                                        if data.get("done"):
                                            sources = data.get("sources", [])
                                            confidence = data.get("confidence", 0.0)
                                    except json.JSONDecodeError:
                                        continue

                    # Final display (remove cursor)
                    response_placeholder.markdown(full_response)

                    if confidence > 0:
                        st.markdown(
                            f'<span class="confidence-badge">🧠 Confiance: {int(confidence * 100)}%</span>',
                            unsafe_allow_html=True,
                        )

                    if sources:
                        render_sources(sources)

                    conv["messages"].append(
                        {
                            "role": "assistant",
                            "content": full_response,
                            "sources": sources,
                            "confidence": confidence,
                        }
                    )
                except Exception as e:
                    response_placeholder.empty()
                    error_msg = f"Impossible de contacter l'agent RAG : {e}"
                    st.error(error_msg)
                    logger.error(error_msg)

        st.session_state.is_generating = False
        st.rerun()


# =====================================================================
# TAB 2: INFRASTRUCTURE ANALYSIS
# =====================================================================
with tab_infra:
    st.markdown("## :material/architecture: Analyse d'Infrastructure")
    st.caption(
        "Uploadez un schéma de votre infrastructure IT et identifiez les composants "
        "concernés par les réglementations européennes (NIS2, DORA, AI Act, RGPD, etc.)"
    )

    infra_file = st.file_uploader(
        "Schéma d'infrastructure ou Document d'architecture (Image, PDF, DOCX)",
        type=["png", "jpg", "jpeg", "svg", "pdf", "docx"],
        key="infra_upload",
    )

    with st.expander("Ajouter un contexte ou une question spécifique (Optionnel)", expanded=False):
        infra_question = st.text_area(
            "Cadrage métier ou interrogation particulière",
            placeholder="Ex: L'entreprise est un point de terminaison bancaire soumis à DORA. Je veux un focus sur... ?",
            height=100,
            label_visibility="collapsed",
        )

    if infra_file:
        if infra_file.type and infra_file.type.startswith("image"):
            st.image(infra_file, caption="Aperçu du schéma", use_container_width=True)

        if st.button(
            ":material/search: Analyser l'infrastructure", use_container_width=True, type="primary"
        ):
            result = None
            with st.status("Analyse en cours...", expanded=True) as status:
                filename_lower = (infra_file.name or "").lower()
                if filename_lower.endswith((".docx", ".pdf")):
                    st.write("📄 Lecture et extraction du document texte...")
                else:
                    st.write("📸 Description de l'infrastructure via modèle vision...")

                try:
                    files = {"file": (infra_file.name, infra_file.getvalue())}
                    data = {"question": infra_question}
                    response = httpx.post(
                        f"{API_URL}/analyze-infrastructure",
                        files=files,
                        data=data,
                        timeout=600,
                    )

                    if response.status_code == 200:
                        result = response.json()
                        status.update(
                            label="Analyse terminée",
                            state="complete",
                            expanded=False,
                        )
                    elif response.status_code == 422:
                        status.update(
                            label=":material/warning: Modèle vision non disponible", state="error"
                        )
                        st.warning(
                            "Le modèle vision (llava) n'est pas installé. "
                            "Lancez : `docker exec -it rag-ollama ollama pull llava`"
                        )
                    else:
                        status.update(label=":material/error: Erreur", state="error")
                        st.error(f"Erreur: {response.text}")
                except Exception as e:
                    status.update(label=":material/error: Erreur de connexion", state="error")
                    st.error(f"Impossible de contacter l'API: {e}")
                    logger.error(f"Erreur analyse infrastructure: {e}")

            # Affichage en dehors de st.status pour éviter de le cacher
            if result:
                st.success(
                    "✅ **Phase de traitement achevée avec succès** - Rapport consolidé ci-dessous"
                )
                st.markdown("### 📊 Analyse de Conformité")
                formatted_report = format_audit_report(result["analysis"])
                st.markdown(formatted_report, unsafe_allow_html=True)

                st.download_button(
                    label=":material/download: Télécharger le rapport (Markdown)",
                    data=result["analysis"],
                    file_name=f"rapport_audit_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                    mime="text/markdown",
                    use_container_width=True,
                    type="primary"
                )

                # Insertion des liens officiels dynamiquement
                links = {
                    "NIS2": "https://cyber.gouv.fr/la-directive-nis-2",
                    "DORA": "https://www.eiopa.europa.eu/digital-operational-resilience-act-dora_en#level-1---regulation-and-amending-directive",
                    "AI Act": "https://artificialintelligenceact.eu/fr/",
                    "RGPD": "https://www.cnil.fr/fr/rgpd-de-quoi-parle-t-on",
                    "CRA": "https://digital-strategy.ec.europa.eu/fr/policies/cyber-resilience-act",
                }

                found_links = []
                analysis_lower = result["analysis"].lower()
                for reg, url in links.items():
                    keyword = reg.lower()
                    if (
                        keyword in analysis_lower
                        or (keyword == "rgpd" and "gdpr" in analysis_lower)
                        or (keyword == "nis2" and "nis 2" in analysis_lower)
                    ):
                        found_links.append(f"- **{reg}** : [{url}]({url})")

                if found_links:
                    with st.expander(
                        "📚 Liens officiels des réglementations mentionnées", expanded=True
                    ):
                        st.markdown("\n".join(found_links))

                with st.expander("📝 Description extraite de l'infrastructure", expanded=False):
                    st.markdown(result["description"])

                if result["confidence"] > 0:
                    st.markdown(
                        f'<span class="confidence-badge">🧠 Confiance: {int(result["confidence"] * 100)}%</span>',
                        unsafe_allow_html=True,
                    )

                if result["sources"]:
                    with st.expander("📎 Sources réglementaires consultées"):
                        for src in result["sources"]:
                            st.markdown(f"**{src['document']}** (Page {src['page'] or 'N/A'})")
                            st.caption(f"_{src['excerpt']}_")
                            score = src["relevance_score"]
                            st.markdown(
                                f'<span class="confidence-badge">🎯 Pertinence: {int(score * 100)}%</span>',
                                unsafe_allow_html=True,
                            )

                conv = get_active_conversation()
                if conv:
                    conv["messages"].append(
                        {
                            "role": "user",
                            "content": f"[Analyse d'infrastructure] {infra_file.name}\n{infra_question or ''}",
                        }
                    )
                    conv["messages"].append(
                        {
                            "role": "assistant",
                            "content": result["analysis"],
                            "sources": result["sources"],
                            "confidence": result["confidence"],
                        }
                    )
                    if conv["title"] == "Nouvelle conversation":
                        conv["title"] = f"Analyse infra — {infra_file.name[:25]}"
    else:
        st.markdown(
            """
        <div class="welcome-card" style="max-width: 500px; margin: 2rem auto;">
            <div class="emoji"><span class="material-symbols-rounded" style="font-size: 3.5rem;">architecture</span></div>
            <div class="card-title">Uploadez votre schéma d'infrastructure</div>
            <div class="card-desc">
                Diagramme réseau, architecture cloud, ou tout schéma technique.<br>
                L'IA identifiera les composants concernés par les réglementations européennes.
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )


# =====================================================================
# TAB 3: COMPLIANCE REPORT
# =====================================================================
with tab_compliance:
    st.markdown("## :material/policy: Rapport de Conformité Automatique")
    st.caption(
        "Générez un rapport d'analyse de conformité basé sur vos documents indexés. "
        "Le système posera automatiquement des questions-clés par réglementation et compilera les résultats."
    )

    # Regulation selector
    available_regs = ["NIS2", "DORA", "RGPD", "AI Act"]
    selected_regs = st.multiselect(
        "Réglementations à analyser",
        options=available_regs,
        default=available_regs,
        help="Sélectionnez les réglementations à inclure dans le rapport",
    )

    # Custom questions
    custom_q = st.text_area(
        "Questions supplémentaires (optionnel)",
        placeholder="Ex: Notre entreprise utilise-t-elle des systèmes d'IA à haut risque ?\n(Une question par ligne)",
        height=80,
    )
    custom_questions = [q.strip() for q in custom_q.split("\n") if q.strip()] if custom_q else None

    col_gen, col_info = st.columns([0.3, 0.7])
    with col_gen:
        generate_report = st.button(
            ":material/rocket: Générer le rapport",
            use_container_width=True,
            type="primary",
            disabled=not selected_regs,
        )
    with col_info:
        if selected_regs:
            n_questions = len(selected_regs) * 3 + (
                len(custom_questions) if custom_questions else 0
            )
            st.caption(
                f"⏱️ Environ {n_questions * 5}-{n_questions * 8} secondes ({n_questions} questions)"
            )

    if generate_report:
        with st.status("Génération du rapport en cours...", expanded=True) as status:
            try:
                st.write(f"📊 Analyse de {len(selected_regs)} réglementations...")
                payload = {"regulations": selected_regs}
                if custom_questions:
                    payload["custom_questions"] = custom_questions

                response = httpx.post(
                    f"{API_URL}/compliance-report",
                    json=payload,
                    timeout=1200,  # Long timeout — multiple RAG queries
                )

                if response.status_code == 200:
                    result = response.json()
                    status.update(label=":material/check_circle: Rapport généré", state="complete")

                    # Build markdown report
                    report_md = "# Rapport de Conformité\n\n"
                    report_md += f"*Généré le {result.get('generated_at', 'N/A')[:10]}*\n\n---\n\n"

                    for section in result["report"]:
                        reg = section["regulation"]
                        st.markdown(f"### 📜 {reg}")
                        report_md += f"## {reg}\n\n"

                        for qa in section["answers"]:
                            confidence_html = ""
                            if qa["confidence"] > 0:
                                confidence_html = f'<div style="margin-top: 0.5rem;"><span class="confidence-badge">🧠 Confiance: {int(qa["confidence"] * 100)}%</span></div>'
                            
                            st.markdown(f"""
                            <div class="dashboard-card">
                                <div style="font-weight: 700; color: var(--primary); margin-bottom: 0.75rem; display: flex; align-items: center; gap: 8px;">
                                    <span class="material-symbols-rounded">help</span> {qa['question']}
                                </div>
                                <div style="font-size: 0.95rem; line-height: 1.6;">
                                    {qa['answer']}
                                </div>
                                {confidence_html}
                            </div>
                            """, unsafe_allow_html=True)
                            
                            if qa["sources"]:
                                render_sources(qa["sources"])

                            report_md += f"### {qa['question']}\n\n{qa['answer']}\n\n"
                            if qa["sources"]:
                                report_md += (
                                    "**Sources:** "
                                    + ", ".join(
                                        f"{s['document']} (p.{s.get('page', 'N/A')})"
                                        for s in qa["sources"]
                                    )
                                    + "\n\n"
                                )
                            report_md += "---\n\n"

                        st.markdown("---")

                    # Export button
                    st.download_button(
                        ":material/download: Exporter le rapport en Markdown",
                        data=report_md,
                        file_name="rapport_conformite.md",
                        mime="text/markdown",
                        use_container_width=True,
                    )

                else:
                    status.update(label=":material/error: Erreur", state="error")
                    st.error(f"Erreur: {response.text}")

            except Exception as e:
                status.update(label=":material/error: Erreur de connexion", state="error")
                st.error(f"Impossible de contacter l'API: {e}")
                logger.error(f"Erreur rapport conformité: {e}")
    elif not selected_regs:
        st.info("Sélectionnez au moins une réglementation pour générer un rapport.")
    else:
        st.markdown(
            """
        <div class="welcome-card" style="max-width: 500px; margin: 2rem auto;">
            <div class="emoji"><span class="material-symbols-rounded" style="font-size: 3.5rem;">policy</span></div>
            <div class="card-title">Rapport de Conformité</div>
            <div class="card-desc">
                Sélectionnez les réglementations ci-dessus et cliquez sur "Générer".<br>
                L'IA analysera vos documents et compilera un rapport structuré.
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
