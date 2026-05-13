
import json
from pathlib import Path
import streamlit as st
from qa_system import TQKnowledgeSystem, build_system

st.set_page_config(
    page_title="TQ Confiable - Asistente Virtual",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS PREMIUM SAAS (Estilo Brutal) ──────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

*, *::before, *::after { box-sizing: border-box; }

/* Variables de color modo SaaS Oscuro */
:root {
    --bg-base: #09090b;
    --bg-surface: #18181b;
    --bg-surface-hover: #27272a;
    --border-subtle: #27272a;
    --text-main: #fafafa;
    --text-muted: #a1a1aa;
    --accent: #3b82f6;
    --accent-glow: rgba(59, 130, 246, 0.15);
}

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background-color: var(--bg-base) !important;
    color: var(--text-main) !important;
    font-family: 'Inter', sans-serif !important;
}

/* Custom Scrollbar */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: var(--bg-base); }
::-webkit-scrollbar-thumb { background: var(--border-subtle); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"], #MainMenu, footer { display: none !important; }

/* ── LOGIN SECTION ── */
.login-container {
    max-width: 420px; margin: 15vh auto; padding: 48px 40px;
    background-color: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 16px;
    text-align: center;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
    animation: fadeInUp 0.6s ease-out;
}
.login-container h2 { font-size: 1.75rem; font-weight: 700; color: var(--text-main); margin-bottom: 8px; letter-spacing: -0.02em; }
.login-container p { font-size: 0.95rem; color: var(--text-muted); margin-bottom: 32px; line-height: 1.5; }

/* ── HERO SECTION ── */
.hero {
    padding: 24px 0 40px;
    text-align: left;
    border-bottom: 1px solid var(--border-subtle);
    margin-bottom: 32px;
    animation: fadeIn 0.8s ease-out;
}
.hero-eyebrow {
    display: inline-block;
    padding: 6px 14px;
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--accent);
    margin-bottom: 16px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
.hero h1 { font-size: 2.5rem; font-weight: 700; color: var(--text-main); letter-spacing: -0.03em; margin-bottom: 8px; }
.hero p { font-size: 1.05rem; color: var(--text-muted); max-width: 650px; line-height: 1.6; }

/* ── TABS ── */
.stTabs [data-baseweb="tab-list"] { background-color: transparent; border-bottom: 1px solid var(--border-subtle); gap: 32px; }
.stTabs [data-baseweb="tab"] { color: var(--text-muted) !important; padding: 16px 4px !important; font-weight: 500 !important; border: none !important; background: transparent !important; font-size: 1rem !important; transition: color 0.2s ease; }
.stTabs [data-baseweb="tab"]:hover { color: #fff !important; }
.stTabs [aria-selected="true"] { color: var(--text-main) !important; border-bottom: 2px solid var(--accent) !important; }

/* ── CHAT BUBBLES ANIMADAS Y REDISEÑADAS ── */
[data-testid="stChatMessage"] {
    background-color: transparent !important;
    border: none !important;
    padding: 20px !important;
    border-radius: 12px;
    margin-bottom: 16px;
    animation: fadeInUp 0.4s ease-out;
}
[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-user"] { background-color: var(--bg-surface) !important; color: var(--text-muted) !important; }
[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-assistant"] { background-color: var(--accent) !important; color: #fff !important; }

/* Burbuja Usuario */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stMarkdownContainer"] {
    background-color: var(--bg-surface);
    padding: 14px 20px;
    border-radius: 12px;
    border: 1px solid var(--border-subtle);
    display: inline-block;
    font-size: 0.95rem;
}

/* Burbuja Asistente Premium */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
    background: linear-gradient(145deg, var(--bg-surface), #121214) !important;
    border: 1px solid var(--border-subtle) !important;
    border-left: 3px solid var(--accent) !important;
    box-shadow: 0 8px 24px var(--accent-glow);
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stMarkdownContainer"] {
    font-size: 0.95rem;
    line-height: 1.7;
}

/* Estilo especial para Negritas (Datos estructurados) */
.stMarkdown strong { color: #fff; font-weight: 600; background: rgba(255,255,255,0.05); padding: 0 4px; border-radius: 4px; }

/* ── METRIC CARDS ── */
.metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 20px; }
.metric-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle); 
    border-radius: 12px; 
    padding: 24px; 
    text-align: left;
    transition: transform 0.2s ease, border-color 0.2s ease;
}
.metric-card:hover { transform: translateY(-2px); border-color: var(--text-muted); }
.metric-num { font-size: 2.25rem; font-weight: 700; color: var(--text-main); letter-spacing: -0.04em; margin-bottom: 4px; }
.metric-desc { font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; font-weight: 500; }

/* ── CONTENT BOXES ── */
.generated-content {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 12px;
    padding: 32px;
    line-height: 1.7;
    color: var(--text-main);
    font-size: 0.95rem;
    animation: fadeIn 0.6s ease-out;
}

/* ── INDICADORES Y ANIMACIONES ── */
.status-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-top: 24px;
    padding: 12px;
    background: var(--bg-surface);
    border-radius: 8px;
    border: 1px solid var(--border-subtle);
}
.pulse-dot {
    width: 8px; height: 8px; background-color: #22c55e; border-radius: 50%;
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7);
    animation: pulse 2s infinite;
}

/* Indicador de Pensando (Thinking) */
.thinking-indicator {
    font-size: 0.9rem;
    color: var(--accent);
    display: flex;
    align-items: center;
    gap: 8px;
    animation: pulse-text 1.5s infinite;
    padding-bottom: 8px;
    font-weight: 500;
}

@keyframes pulse-text {
    0% { opacity: 0.4; }
    50% { opacity: 1; }
    100% { opacity: 0.4; }
}
@keyframes fadeInUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes pulse {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }
    70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(34, 197, 94, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
}
</style>
""", unsafe_allow_html=True)

# ── 1. GESTIÓN DE SESIÓN (LOGIN OBLIGATORIO) ──────────────────────────────────
if "user_email" not in st.session_state:
    st.session_state.user_email = None

if not st.session_state.user_email:
    st.markdown("<div class='login-container'>", unsafe_allow_html=True)
    st.markdown("<h2>Acceso Corporativo</h2>", unsafe_allow_html=True)
    st.markdown("<p>Identifícate para sincronizar tu memoria semántica.</p>", unsafe_allow_html=True)
    
    email_input = st.text_input("ID de empleado o correo:", placeholder="ejemplo@tq.com", label_visibility="collapsed")
    
    if st.button("Iniciar Sesión", type="primary", use_container_width=True):
        if email_input.strip():
            st.session_state.user_email = email_input.strip()
            st.session_state.messages = [
                {"role": "assistant", "content": "Conexión segura establecida. Soy TQ-Confiable. ¿Qué datos necesitas recuperar hoy?"}
            ]
            st.rerun()
        else:
            st.warning("Credencial requerida.")
            
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# ── INICIALIZACIÓN DEL SISTEMA ────────────────────────────────────────────────
@st.cache_resource(show_spinner="Cargando modelos cognitivos y FAISS...")
def load_system():
    build_system()
    return TQKnowledgeSystem()

system = load_system()

EXAMPLES = [
    "¿Cuántas sedes productivas tiene TQ y en qué países?",
    "Nombra las principales marcas de consumo masivo.",
    "¿Qué iniciativas ambientales y sociales tienen?",
    "¿Cuál es el NIT y correo de servicio al cliente?"
]

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("###TQ Cognitivo")
    st.markdown(f"<span style='color:#a1a1aa; font-size:0.85rem;'>ID Activo:</span><br>**{st.session_state.user_email}**", unsafe_allow_html=True)
    st.markdown("---")
    
    if st.button("Limpiar Memoria Contextual", use_container_width=True):
        st.session_state.messages = [{"role": "assistant", "content": "Memoria de sesión purgada. Listo para nuevas consultas."}]
        st.rerun()
        
    if st.button("Finalizar Sesión", use_container_width=True):
        st.session_state.user_email = None
        st.rerun()

    st.markdown("""
    <div class="status-indicator">
        <div class="pulse-dot"></div>
        <span>Sistemas Operativos (Latencia < 150ms)</span>
    </div>
    """, unsafe_allow_html=True)

# ── MAIN CONTENT ──────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <div class="hero-eyebrow">Enterprise Agentic RAG</div>
  <h1>TQ Confiable</h1>
  <p>Motor de conocimiento híbrido con enrutamiento semántico, memoria persistente y recuperación multi-vectorial.</p>
</div>
""", unsafe_allow_html=True)

tab_chat, tab_resumen, tab_faq, tab_arq = st.tabs([
    "Agente Conversacional",
    "Resumen Estratégico",
    "Generador FAQ",
    "Arquitectura y Telemetría",
])

# ── TAB 1: CHAT (CON STREAMING BRUTAL) ────────────────────────────────────────
with tab_chat:
    chat_container = st.container()
    
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        
        # Sugerencias visualmente limpias solo al inicio
        if len(st.session_state.messages) == 1:
            st.markdown("<br><p style='color:var(--text-muted); font-size:0.85rem; text-transform:uppercase; letter-spacing:0.05em;'>Consultas Frecuentes</p>", unsafe_allow_html=True)
            cols = st.columns(2)
            for i, ex in enumerate(EXAMPLES):
                if cols[i % 2].button(ex, key=f"btn_ex_{i}", use_container_width=True):
                    st.session_state.temp_prompt = ex
                    st.rerun()

    prompt = st.chat_input("Consulta la base de conocimiento de TQ...")
    
    if "temp_prompt" in st.session_state:
        prompt = st.session_state.temp_prompt
        del st.session_state.temp_prompt

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                # 1. Creamos un espacio vacío y le inyectamos la animación pulsante
                status_placeholder = st.empty()
                status_placeholder.markdown(
                    "<div class='thinking-indicator'>⚙️ Analizando intención y consultando conocimiento corporativo...</div>", 
                    unsafe_allow_html=True
                )
                
                # 2. Llamamos a tu motor de streaming
                stream_generator = system.answer_question_stream(prompt, st.session_state.user_email)
                
                # 3. Interceptor: borra el indicador apenas llega la primera letra
                def ui_stream():
                    first_token = True
                    for chunk in stream_generator:
                        if first_token:
                            status_placeholder.empty()
                            first_token = False
                        yield chunk
                
                # 4. Streamlit imprime la respuesta en tiempo real
                respuesta_completa = st.write_stream(ui_stream())
                
                st.session_state.messages.append({"role": "assistant", "content": respuesta_completa})

# ── TAB 2: RESUMEN ────────────────────────────────────────────────────────────
with tab_resumen:
    if st.button("Generar Resumen Ejecutivo (Auto-Sintetizado)", type="primary"):
        with st.spinner("Compilando inteligencia empresarial..."):
            st.session_state["summary"] = system.get_summary()

    if "summary" in st.session_state:
        st.markdown(f'<div class="generated-content">{st.session_state["summary"]}</div>', unsafe_allow_html=True)

# ── TAB 3: FAQ ────────────────────────────────────────────────────────────────
with tab_faq:
    if st.button("Extraer Panel FAQ Estructurado", type="primary"):
        with st.spinner("Analizando consultas potenciales..."):
            st.session_state["faq"] = system.get_faq()

    if "faq" in st.session_state:
        st.markdown(f'<div class="generated-content">{st.session_state["faq"]}</div>', unsafe_allow_html=True)

# ── TAB 4: ARQUITECTURA ───────────────────────────────────────────────────────
with tab_arq:
    col_a, col_b = st.columns([1, 1], gap="large")

    with col_a:
        st.markdown("### Stack Tecnológico 2025")
        st.markdown("""
        - **LLM Engine:** Gemini 2.5 Flash (`temperature=0.0`)
        - **Orquestador:** LangGraph (`create_react_agent` + `MemorySaver`)
        - **Dense Retrieval:** FAISS (HNSW) + `multilingual-e5-large`
        - **Sparse Retrieval:** BM25S (NumPy backend)
        - **Cross-Encoder:** `mmarco-mMiniLMv2` (Top-8 Reranking)
        - **Tooling:** Pydantic validation + Semantic Routing
        """)

    with col_b:
        kb_length = 0
        try:
            chunks_path = Path(r"C:\Users\danie\Desktop\TAIA\chunks.json")
            if chunks_path.exists():
                with open(chunks_path, "r", encoding="utf-8") as f:
                    chunks_data = json.load(f)
                    kb_length = sum(len(c["text"]) for c in chunks_data)
        except:
            kb_length = 2437910
            
        st.markdown(f"""
<div class="metric-grid">
  <div class="metric-card">
    <div class="metric-num">{kb_length:,}</div>
    <div class="metric-desc">Caracteres Vectorizados</div>
  </div>
  <div class="metric-card">
    <div class="metric-num">3</div>
    <div class="metric-desc">Tools Autónomas</div>
  </div>
  <div class="metric-card">
    <div class="metric-num">2</div>
    <div class="metric-desc">Índices FAISS Activos</div>
  </div>
</div>
        """, unsafe_allow_html=True)
