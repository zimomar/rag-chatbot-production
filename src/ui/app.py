"""
Interface utilisateur Streamlit pour le Chatbot RAG Local.
Design glassmorphique premium avec mode clair/sombre,
historique de conversations et analyse d'infrastructure.
"""

import json
import logging
import os
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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');



    @keyframes fadeSlideIn {
        from { opacity: 0; transform: translateY(12px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes typingPulse {
        0%, 60%, 100% { opacity: 0.3; transform: scale(0.8); }
        30% { opacity: 1; transform: scale(1.1); }
    }

    #MainMenu, footer { visibility: hidden; }

    .typing-indicator {
        display: flex; align-items: center; gap: 6px; padding: 0.5rem 1rem;
    }
    .typing-indicator .dot {
        width: 8px; height: 8px; border-radius: 50%;
        animation: typingPulse 1.4s ease-in-out infinite;
    }
    .typing-indicator .dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-indicator .dot:nth-child(3) { animation-delay: 0.4s; }

    .welcome-card {
        border-radius: 16px; padding: 1.5rem; cursor: pointer;
        transition: all 0.3s ease; text-align: center;
    }
    .welcome-card:hover { transform: translateY(-4px); }
    .welcome-card .emoji { font-size: 2rem; margin-bottom: 0.5rem; }
    .welcome-card .card-title { font-weight: 600; font-size: 0.95rem; margin-bottom: 0.25rem; }
    .welcome-card .card-desc { font-size: 0.8rem; }

    .hero-section { text-align: center; padding: 3rem 1rem; animation: fadeSlideIn 0.6s ease-out; }
    .hero-section h1 { font-size: 2.5rem !important; margin-bottom: 0.5rem !important; }

    .confidence-badge {
        display: inline-flex; align-items: center; gap: 6px;
        border-radius: 20px; padding: 4px 12px; font-size: 0.8rem;
    }

    .conv-title {
        font-weight: 500; font-size: 0.85rem;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .conv-date { font-size: 0.7rem; }

    [data-testid="stChatMessage"] {
        border-radius: 16px !important;
        animation: fadeSlideIn 0.4s ease-out !important;
        margin-bottom: 1rem !important;
    }

    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }

    /* Theme toggle styling */
    .theme-toggle-label {
        font-size: 0.85rem;
        font-weight: 500;
    }
</style>
"""

# --- Dark Theme CSS ---
DARK_CSS = """
<style>
    .stApp, .stAppViewContainer, .stMain {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 30%, #1e293b 60%, #0c1445 100%) !important;
        background-attachment: fixed !important;
    }
    .stAppHeader {
        background: rgba(15, 23, 42, 0.8) !important;
        backdrop-filter: blur(20px) !important;
        border-bottom: 1px solid rgba(255,255,255,0.06) !important;
    }

    [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {
        background: rgba(15, 23, 42, 0.85) !important;
        backdrop-filter: blur(24px) saturate(180%) !important;
        border-right: 1px solid rgba(255,255,255,0.08) !important;
    }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #f8fafc !important; -webkit-text-fill-color: #f8fafc !important; background: none !important;
    }

    [data-testid="stSidebar"] .stButton > button {
        background: rgba(59, 130, 246, 0.15) !important;
        border: 1px solid rgba(59, 130, 246, 0.3) !important;
        color: #93c5fd !important; border-radius: 10px !important;
        backdrop-filter: blur(10px) !important; transition: all 0.3s ease !important; font-weight: 500 !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(59, 130, 246, 0.3) !important;
        border-color: rgba(59, 130, 246, 0.6) !important;
        box-shadow: 0 0 20px rgba(59, 130, 246, 0.2) !important;
        transform: translateY(-1px) !important;
    }

    [data-testid="stChatMessage"] {
        background: rgba(255, 255, 255, 0.05) !important;
        backdrop-filter: blur(16px) saturate(150%) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
        color: #e2e8f0 !important;
    }
    [data-testid="stChatMessage"]:has(div[data-testid="user-avatar"]) {
        background: rgba(59, 130, 246, 0.08) !important;
        border-color: rgba(59, 130, 246, 0.15) !important;
    }
    [data-testid="stChatMessage"] * { color: #e2e8f0 !important; }

    div[data-testid="stBottom"] {
        background: rgba(15, 23, 42, 0.6) !important; backdrop-filter: blur(20px) !important;
    }
    div[data-testid="stBottom"] > div { background: transparent !important; }
    [data-testid="stChatInput"] {
        background: rgba(255, 255, 255, 0.06) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 14px !important;
        box-shadow: 0 2px 16px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
        backdrop-filter: blur(12px) !important;
    }
    [data-testid="stChatInput"] textarea { color: #f1f5f9 !important; background: transparent !important; }
    [data-testid="stChatInput"] textarea::placeholder { color: rgba(148, 163, 184, 0.6) !important; }
    [data-testid="stChatInput"] button {
        background: linear-gradient(135deg, #3b82f6, #06b6d4) !important;
        color: white !important; border-radius: 10px !important; border: none !important;
        transition: all 0.3s ease !important;
    }
    [data-testid="stChatInput"] button:hover {
        box-shadow: 0 0 16px rgba(59, 130, 246, 0.4) !important; transform: scale(1.05) !important;
    }

    [data-testid="stFileUploader"] {
        background: rgba(255, 255, 255, 0.04) !important;
        border: 2px dashed rgba(148, 163, 184, 0.2) !important;
        border-radius: 12px !important; padding: 10px !important;
        backdrop-filter: blur(8px) !important; transition: all 0.3s ease !important;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: rgba(59, 130, 246, 0.4) !important; background: rgba(59, 130, 246, 0.05) !important;
    }
    [data-testid="stFileUploader"] section { background: transparent !important; }
    [data-testid="stFileUploader"] [data-testid="baseButton-secondary"] {
        background: rgba(255, 255, 255, 0.08) !important; color: #93c5fd !important;
        border: 1px solid rgba(59, 130, 246, 0.25) !important; border-radius: 8px !important;
        transition: all 0.3s ease !important;
    }
    [data-testid="stFileUploader"] [data-testid="baseButton-secondary"]:hover {
        background: rgba(59, 130, 246, 0.15) !important; border-color: #3b82f6 !important;
    }
    [data-testid="stFileUploader"] label { color: #94a3b8 !important; }

    [data-testid="stExpander"] {
        background: rgba(255, 255, 255, 0.04) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important; backdrop-filter: blur(8px) !important;
    }
    [data-testid="stExpander"] summary { color: #93c5fd !important; }

    .stProgress > div > div { background: rgba(255,255,255,0.08) !important; border-radius: 8px !important; }
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #3b82f6, #06b6d4) !important; border-radius: 8px !important;
    }

    .main h1, .main h2, .main h3 { color: #f8fafc !important; }
    .main h1 {
        font-weight: 800 !important;
        background: linear-gradient(135deg, #f8fafc, #3b82f6, #06b6d4) !important;
        -webkit-background-clip: text !important; -webkit-text-fill-color: transparent !important;
        background-clip: text !important;
    }
    .main p, .main span, .main div, .main li { color: #cbd5e1 !important; }

    [data-testid="stStatusWidget"], .stAlert {
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: 10px !important; backdrop-filter: blur(12px) !important; color: #e2e8f0 !important;
    }

    .stTabs [data-baseweb="tab-list"] { gap: 8px !important; background: transparent !important; }
    .stTabs [data-baseweb="tab"] {
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: 10px 10px 0 0 !important; color: #94a3b8 !important;
        backdrop-filter: blur(8px) !important;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(59, 130, 246, 0.15) !important;
        border-color: rgba(59, 130, 246, 0.3) !important; color: #93c5fd !important;
    }
    hr { border-color: rgba(255,255,255,0.08) !important; }

    .welcome-card {
        background: rgba(255, 255, 255, 0.05); backdrop-filter: blur(16px) saturate(150%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.05);
    }
    .welcome-card:hover {
        background: rgba(59, 130, 246, 0.1); border-color: rgba(59, 130, 246, 0.3);
        box-shadow: 0 8px 32px rgba(59, 130, 246, 0.15);
    }
    .welcome-card .card-title { color: #f1f5f9 !important; }
    .welcome-card .card-desc { color: #94a3b8 !important; }
    .hero-subtitle { color: #94a3b8 !important; }
    .confidence-badge {
        background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.2); color: #93c5fd !important;
    }
    .typing-indicator .dot { background: #3b82f6; }
    .conv-title { color: #e2e8f0 !important; }
    .conv-date { color: #64748b !important; }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
</style>
"""

# --- Light Theme CSS ---
LIGHT_CSS = """
<style>
    .stApp, .stAppViewContainer, .stMain {
        background: linear-gradient(135deg, #f0f4ff 0%, #e8eef9 30%, #f8fafc 60%, #eef2ff 100%) !important;
        background-attachment: fixed !important;
    }
    .stAppHeader {
        background: rgba(255, 255, 255, 0.8) !important;
        backdrop-filter: blur(20px) !important;
        border-bottom: 1px solid rgba(0,0,0,0.06) !important;
    }

    [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {
        background: rgba(255, 255, 255, 0.75) !important;
        backdrop-filter: blur(24px) saturate(180%) !important;
        border-right: 1px solid rgba(0,0,0,0.08) !important;
    }
    [data-testid="stSidebar"] * { color: #334155 !important; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #1e293b !important; -webkit-text-fill-color: #1e293b !important; background: none !important;
    }

    [data-testid="stSidebar"] .stButton > button {
        background: rgba(59, 130, 246, 0.08) !important;
        border: 1px solid rgba(59, 130, 246, 0.2) !important;
        color: #2563eb !important; border-radius: 10px !important;
        backdrop-filter: blur(10px) !important; transition: all 0.3s ease !important; font-weight: 500 !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(59, 130, 246, 0.15) !important;
        border-color: rgba(59, 130, 246, 0.4) !important;
        box-shadow: 0 0 16px rgba(59, 130, 246, 0.12) !important;
        transform: translateY(-1px) !important;
    }

    [data-testid="stChatMessage"] {
        background: rgba(255, 255, 255, 0.7) !important;
        backdrop-filter: blur(16px) saturate(150%) !important;
        border: 1px solid rgba(0, 0, 0, 0.06) !important;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04), inset 0 1px 0 rgba(255, 255, 255, 0.8) !important;
        color: #1e293b !important;
    }
    [data-testid="stChatMessage"]:has(div[data-testid="user-avatar"]) {
        background: rgba(239, 246, 255, 0.8) !important;
        border-color: rgba(59, 130, 246, 0.1) !important;
    }
    [data-testid="stChatMessage"] * { color: #1e293b !important; }

    div[data-testid="stBottom"] {
        background: rgba(248, 250, 252, 0.7) !important; backdrop-filter: blur(20px) !important;
    }
    div[data-testid="stBottom"] > div { background: transparent !important; }
    [data-testid="stChatInput"] {
        background: rgba(255, 255, 255, 0.8) !important;
        border: 1px solid rgba(0, 0, 0, 0.1) !important;
        border-radius: 14px !important;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.9) !important;
        backdrop-filter: blur(12px) !important;
    }
    [data-testid="stChatInput"] textarea { color: #1e293b !important; background: transparent !important; }
    [data-testid="stChatInput"] textarea::placeholder { color: rgba(100, 116, 139, 0.6) !important; }
    [data-testid="stChatInput"] button {
        background: linear-gradient(135deg, #3b82f6, #06b6d4) !important;
        color: white !important; border-radius: 10px !important; border: none !important;
        transition: all 0.3s ease !important;
    }
    [data-testid="stChatInput"] button:hover {
        box-shadow: 0 0 16px rgba(59, 130, 246, 0.3) !important; transform: scale(1.05) !important;
    }

    [data-testid="stFileUploader"] {
        background: rgba(255, 255, 255, 0.5) !important;
        border: 2px dashed rgba(100, 116, 139, 0.25) !important;
        border-radius: 12px !important; padding: 10px !important;
        backdrop-filter: blur(8px) !important; transition: all 0.3s ease !important;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: rgba(59, 130, 246, 0.4) !important; background: rgba(239, 246, 255, 0.5) !important;
    }
    [data-testid="stFileUploader"] section { background: transparent !important; }
    [data-testid="stFileUploader"] [data-testid="baseButton-secondary"] {
        background: rgba(255, 255, 255, 0.8) !important; color: #2563eb !important;
        border: 1px solid rgba(59, 130, 246, 0.2) !important; border-radius: 8px !important;
        transition: all 0.3s ease !important;
    }
    [data-testid="stFileUploader"] [data-testid="baseButton-secondary"]:hover {
        background: rgba(239, 246, 255, 0.8) !important; border-color: #3b82f6 !important;
    }
    [data-testid="stFileUploader"] label { color: #64748b !important; }

    /* ============ TEXT AREA / INPUTS ============ */
    [data-testid="stTextArea"] textarea,
    .stTextArea textarea,
    .stTextInput input {
        background: rgba(255, 255, 255, 0.8) !important;
        color: #1e293b !important;
        border: 1px solid rgba(0, 0, 0, 0.1) !important;
        border-radius: 10px !important;
        backdrop-filter: blur(8px) !important;
    }
    [data-testid="stTextArea"] textarea::placeholder,
    .stTextArea textarea::placeholder,
    .stTextInput input::placeholder {
        color: rgba(100, 116, 139, 0.6) !important;
    }
    [data-testid="stTextArea"] label,
    .stTextArea label,
    .stTextInput label {
        color: #475569 !important;
    }

    [data-testid="stExpander"] {
        background: rgba(255, 255, 255, 0.5) !important;
        border: 1px solid rgba(0, 0, 0, 0.06) !important;
        border-radius: 12px !important; backdrop-filter: blur(8px) !important;
    }
    [data-testid="stExpander"] summary { color: #2563eb !important; }

    .stProgress > div > div { background: rgba(0,0,0,0.06) !important; border-radius: 8px !important; }
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #3b82f6, #06b6d4) !important; border-radius: 8px !important;
    }

    .main h1, .main h2, .main h3 { color: #1e293b !important; }
    .main h1 {
        font-weight: 800 !important;
        background: linear-gradient(135deg, #1e293b, #3b82f6, #06b6d4) !important;
        -webkit-background-clip: text !important; -webkit-text-fill-color: transparent !important;
        background-clip: text !important;
    }
    .main p, .main span, .main div, .main li { color: #475569 !important; }

    [data-testid="stStatusWidget"], .stAlert {
        background: rgba(255,255,255,0.6) !important;
        border: 1px solid rgba(0,0,0,0.06) !important;
        border-radius: 10px !important; backdrop-filter: blur(12px) !important; color: #334155 !important;
    }

    .stTabs [data-baseweb="tab-list"] { gap: 8px !important; background: transparent !important; }
    .stTabs [data-baseweb="tab"] {
        background: rgba(255,255,255,0.5) !important;
        border: 1px solid rgba(0,0,0,0.06) !important;
        border-radius: 10px 10px 0 0 !important; color: #64748b !important;
        backdrop-filter: blur(8px) !important;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(59, 130, 246, 0.08) !important;
        border-color: rgba(59, 130, 246, 0.2) !important; color: #2563eb !important;
    }
    hr { border-color: rgba(0,0,0,0.08) !important; }

    .welcome-card {
        background: rgba(255, 255, 255, 0.6); backdrop-filter: blur(16px) saturate(150%);
        border: 1px solid rgba(0, 0, 0, 0.06);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05), inset 0 1px 0 rgba(255, 255, 255, 0.8);
    }
    .welcome-card:hover {
        background: rgba(239, 246, 255, 0.8); border-color: rgba(59, 130, 246, 0.2);
        box-shadow: 0 8px 32px rgba(59, 130, 246, 0.1);
    }
    .welcome-card .card-title { color: #1e293b !important; }
    .welcome-card .card-desc { color: #64748b !important; }
    .hero-subtitle { color: #64748b !important; }
    .confidence-badge {
        background: rgba(59, 130, 246, 0.08); border: 1px solid rgba(59, 130, 246, 0.15); color: #2563eb !important;
    }
    .typing-indicator .dot { background: #3b82f6; }
    .conv-title { color: #334155 !important; }
    .conv-date { color: #94a3b8 !important; }
    ::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.12); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,0.2); }
</style>
"""

# Inject CSS
st.markdown(SHARED_CSS, unsafe_allow_html=True)
st.markdown(DARK_CSS if is_dark else LIGHT_CSS, unsafe_allow_html=True)

# Configuration de l'URL API
API_URL = os.getenv("API_URL", "http://api:8000")
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
                    <div class="emoji"><span class="material-symbols-rounded" style="font-size: 2.5rem;">{emoji}</span></div>
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
            if "sources" in message and message["sources"]:
                with st.expander("📎 Sources consultées"):
                    for src in message["sources"]:
                        st.markdown(f"**{src['document']}** (Page {src['page'] or 'N/A'})")
                        st.caption(f"_{src['excerpt']}_")
                        score = src["relevance_score"]
                        st.markdown(
                            f'<span class="confidence-badge">🎯 Pertinence: {int(score * 100)}%</span>',
                            unsafe_allow_html=True,
                        )
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
                        with st.expander("📎 Sources consultées"):
                            for src in sources:
                                st.markdown(f"**{src['document']}** (Page {src['page'] or 'N/A'})")
                                st.caption(f"_{src['excerpt']}_")
                                score = src["relevance_score"]
                                st.markdown(
                                    f'<span class="confidence-badge">🎯 Pertinence: {int(score * 100)}%</span>',
                                    unsafe_allow_html=True,
                                )

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

    col_upload, col_question = st.columns([1, 1])

    with col_upload:
        infra_file = st.file_uploader(
            "Schéma d'infrastructure ou Document d'architecture (Image, PDF, DOCX)",
            type=["png", "jpg", "jpeg", "svg", "pdf", "docx"],
            key="infra_upload",
        )

    with col_question:
        infra_question = st.text_area(
            "Question spécifique (optionnel)",
            placeholder="Ex: Quels composants de mon infrastructure sont impactés par NIS2 ?",
            height=100,
        )

    if infra_file:
        if infra_file.type and infra_file.type.startswith("image"):
            st.image(infra_file, caption="Aperçu du schéma", use_container_width=True)

        if st.button(
            ":material/search: Analyser l'infrastructure", use_container_width=True, type="primary"
        ):
            with st.status("Analyse en cours...", expanded=True) as status:
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
                            label=":material/check_circle: Analyse terminée", state="complete"
                        )

                        with st.expander(
                            "📝 Description extraite de l'infrastructure", expanded=False
                        ):
                            st.markdown(result["description"])

                        st.markdown("### 📊 Analyse de Conformité")
                        st.markdown(result["analysis"])

                        if result["confidence"] > 0:
                            st.markdown(
                                f'<span class="confidence-badge">🧠 Confiance: {int(result["confidence"] * 100)}%</span>',
                                unsafe_allow_html=True,
                            )

                        if result["sources"]:
                            with st.expander("📎 Sources réglementaires consultées"):
                                for src in result["sources"]:
                                    st.markdown(
                                        f"**{src['document']}** (Page {src['page'] or 'N/A'})"
                                    )
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
    else:
        st.markdown(
            """
        <div class="welcome-card" style="max-width: 500px; margin: 2rem auto;">
            <div class="emoji"><span class="material-symbols-rounded" style="font-size: 3rem;">architecture</span></div>
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
                            with st.expander(f":material/help: {qa['question']}", expanded=False):
                                st.markdown(qa["answer"])
                                if qa["confidence"] > 0:
                                    st.markdown(
                                        f'<span class="confidence-badge">🧠 Confiance: {int(qa["confidence"] * 100)}%</span>',
                                        unsafe_allow_html=True,
                                    )
                                if qa["sources"]:
                                    st.caption(
                                        "Sources: "
                                        + ", ".join(
                                            f"{s['document']} (p.{s.get('page', 'N/A')})"
                                            for s in qa["sources"]
                                        )
                                    )

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
            <div class="emoji"><span class="material-symbols-rounded" style="font-size: 3rem;">policy</span></div>
            <div class="card-title">Rapport de Conformité</div>
            <div class="card-desc">
                Sélectionnez les réglementations ci-dessus et cliquez sur "Générer".<br>
                L'IA analysera vos documents et compilera un rapport structuré.
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
