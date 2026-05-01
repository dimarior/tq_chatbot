"""
app.py
Interfaz Streamlit premium para el Sistema Q&A de TQ Confiable - Tecnoquimicas.
Ejecutar: python -m streamlit run app.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from qa_system import TQKnowledgeSystem
st.set_page_config(
    page_title="TQ Confiable - Asistente Virtual",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700;800&family=DM+Sans:wght@300;400;500;600&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background: #04080f !important;
    color: #e8eaf0 !important;
    font-family: 'DM Sans', sans-serif !important;
}

[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(ellipse 80% 50% at 20% -10%, rgba(0,82,204,0.18) 0%, transparent 60%),
        radial-gradient(ellipse 60% 40% at 80% 110%, rgba(0,160,220,0.12) 0%, transparent 55%),
        #04080f !important;
}

[data-testid="stHeader"], [data-testid="stToolbar"] { display: none !important; }
#MainMenu, footer, header { visibility: hidden !important; }
[data-testid="stSidebar"] { display: none !important; }

section[data-testid="stMain"] > div { padding: 0 !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* ── HERO ── */
.hero {
    position: relative;
    overflow: hidden;
    padding: 56px 64px 52px;
    background:
        linear-gradient(135deg, rgba(0,40,120,0.95) 0%, rgba(0,82,180,0.9) 45%, rgba(0,140,210,0.85) 100%);
    border-bottom: 1px solid rgba(255,255,255,0.08);
}
.hero::before {
    content: '';
    position: absolute;
    inset: 0;
    background:
        repeating-linear-gradient(
            0deg,
            transparent,
            transparent 39px,
            rgba(255,255,255,0.025) 39px,
            rgba(255,255,255,0.025) 40px
        ),
        repeating-linear-gradient(
            90deg,
            transparent,
            transparent 39px,
            rgba(255,255,255,0.025) 39px,
            rgba(255,255,255,0.025) 40px
        );
    pointer-events: none;
}
.hero::after {
    content: '';
    position: absolute;
    top: -80px; right: -80px;
    width: 400px; height: 400px;
    background: radial-gradient(circle, rgba(0,200,255,0.15) 0%, transparent 65%);
    pointer-events: none;
}
.hero-inner {
    position: relative;
    z-index: 1;
    max-width: 900px;
    margin: 0 auto;
    text-align: center;
}
.hero-eyebrow {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: rgba(255,255,255,0.1);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 100px;
    padding: 5px 16px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(255,255,255,0.85);
    margin-bottom: 20px;
}
.hero-eyebrow span { width: 6px; height: 6px; border-radius: 50%; background: #4dd9ff; display: inline-block; animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.5;transform:scale(0.8)} }
.hero h1 {
    font-family: 'Playfair Display', serif;
    font-size: clamp(2.2rem, 4vw, 3.4rem);
    font-weight: 800;
    color: #ffffff;
    line-height: 1.1;
    letter-spacing: -0.02em;
    margin-bottom: 14px;
}
.hero h1 em { font-style: normal; color: #4dd9ff; }
.hero-sub {
    font-size: 1.05rem;
    font-weight: 300;
    color: rgba(255,255,255,0.78);
    line-height: 1.6;
    margin-bottom: 28px;
}
.hero-stats {
    display: flex;
    justify-content: center;
    gap: 32px;
    flex-wrap: wrap;
}
.hero-stat {
    text-align: center;
}
.hero-stat strong {
    display: block;
    font-family: 'Playfair Display', serif;
    font-size: 1.6rem;
    font-weight: 700;
    color: #ffffff;
}
.hero-stat span {
    font-size: 0.72rem;
    color: rgba(255,255,255,0.55);
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
.hero-divider { width: 1px; height: 40px; background: rgba(255,255,255,0.2); align-self: center; }

/* ── MAIN CONTENT ── */
.main-wrap {
    max-width: 1280px;
    margin: 0 auto;
    padding: 40px 48px 60px;
}

/* ── TABS ── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid rgba(255,255,255,0.08) !important;
    gap: 0 !important;
    padding: 0 !important;
    margin-bottom: 36px !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: rgba(255,255,255,0.45) !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
    padding: 14px 28px !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    transition: all 0.2s !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: rgba(255,255,255,0.8) !important;
}
.stTabs [aria-selected="true"] {
    color: #4dd9ff !important;
    border-bottom: 2px solid #4dd9ff !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }
.stTabs [data-baseweb="tab-border"] { display: none !important; }

/* ── SECTION TITLE ── */
.section-title {
    font-family: 'Playfair Display', serif;
    font-size: 1.6rem;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 6px;
}
.section-sub {
    font-size: 0.88rem;
    color: rgba(255,255,255,0.45);
    margin-bottom: 28px;
    line-height: 1.5;
}

/* ── INPUT ── */
.stTextArea textarea {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 12px !important;
    color: #e8eaf0 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.95rem !important;
    padding: 16px !important;
    transition: border-color 0.2s !important;
    resize: none !important;
}
.stTextArea textarea:focus {
    border-color: rgba(77,217,255,0.4) !important;
    box-shadow: 0 0 0 3px rgba(77,217,255,0.06) !important;
}
.stTextArea textarea::placeholder { color: rgba(255,255,255,0.25) !important; }
label[data-testid="stWidgetLabel"] p {
    color: rgba(255,255,255,0.55) !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    margin-bottom: 8px !important;
}

/* ── BUTTONS ── */
.stButton > button {
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 600 !important;
    border-radius: 10px !important;
    transition: all 0.2s !important;
    border: none !important;
    letter-spacing: 0.02em !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #0052cc, #0099e6) !important;
    color: #ffffff !important;
    padding: 14px 32px !important;
    font-size: 0.9rem !important;
    box-shadow: 0 4px 20px rgba(0,82,204,0.35) !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #0040aa, #007acc) !important;
    box-shadow: 0 6px 28px rgba(0,82,204,0.5) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"] {
    background: rgba(255,255,255,0.05) !important;
    color: rgba(255,255,255,0.6) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    padding: 14px 24px !important;
    font-size: 0.88rem !important;
}
.stButton > button[kind="secondary"]:hover {
    background: rgba(255,255,255,0.09) !important;
    color: #ffffff !important;
    border-color: rgba(255,255,255,0.2) !important;
}

/* Ejemplo buttons */
.example-btn > button {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    color: rgba(255,255,255,0.5) !important;
    font-size: 0.78rem !important;
    font-weight: 400 !important;
    padding: 9px 14px !important;
    border-radius: 8px !important;
    text-align: left !important;
    width: 100% !important;
    margin-bottom: 2px !important;
}
.example-btn > button:hover {
    background: rgba(77,217,255,0.06) !important;
    border-color: rgba(77,217,255,0.2) !important;
    color: #4dd9ff !important;
}

/* ── ANSWER BOX ── */
.answer-wrap {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 16px;
    padding: 28px 32px;
    margin-top: 8px;
    min-height: 140px;
    position: relative;
    overflow: hidden;
}
.answer-wrap::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, #0052cc, #4dd9ff, transparent);
}
.answer-label {
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #4dd9ff;
    margin-bottom: 14px;
}
.answer-text {
    font-size: 0.97rem;
    line-height: 1.8;
    color: #c8d0e0;
    white-space: pre-wrap;
}
.answer-placeholder {
    font-size: 0.9rem;
    color: rgba(255,255,255,0.18);
    font-style: italic;
}

/* ── EXAMPLES PANEL ── */
.examples-label {
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(255,255,255,0.35);
    margin-bottom: 12px;
    padding-left: 2px;
}

/* ── METRIC CARDS ── */
.metric-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
    margin-bottom: 8px;
}
.metric-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 12px;
    padding: 20px 24px;
    position: relative;
    overflow: hidden;
}
.metric-card::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, #0052cc, transparent);
}
.metric-num {
    font-family: 'Playfair Display', serif;
    font-size: 2rem;
    font-weight: 700;
    color: #ffffff;
    line-height: 1;
    margin-bottom: 4px;
}
.metric-desc {
    font-size: 0.78rem;
    color: rgba(255,255,255,0.4);
    line-height: 1.4;
}

/* ── TABLE ── */
.stMarkdown table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
    margin: 16px 0;
}
.stMarkdown th {
    background: rgba(0,82,204,0.2) !important;
    color: #4dd9ff !important;
    font-weight: 600 !important;
    padding: 12px 16px !important;
    text-align: left !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    font-size: 0.8rem !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
}
.stMarkdown td {
    padding: 11px 16px !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    color: rgba(255,255,255,0.7) !important;
    vertical-align: top !important;
}
.stMarkdown tr:nth-child(even) td { background: rgba(255,255,255,0.02) !important; }

/* ── CODE BLOCK ── */
.stMarkdown pre {
    background: rgba(0,0,0,0.4) !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 10px !important;
    padding: 20px 24px !important;
    color: #a8d8ff !important;
    font-size: 0.82rem !important;
    line-height: 1.7 !important;
}

/* ── SPINNER ── */
[data-testid="stSpinner"] p { color: rgba(255,255,255,0.5) !important; }

/* ── GENERATED CONTENT ── */
.generated-content {
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 16px;
    padding: 32px 36px;
    margin-top: 8px;
    line-height: 1.8;
    color: #c8d0e0;
    font-size: 0.95rem;
}

/* ── FOOTER ── */
.tq-footer {
    text-align: center;
    padding: 32px 0 16px;
    border-top: 1px solid rgba(255,255,255,0.05);
    margin-top: 48px;
    color: rgba(255,255,255,0.2);
    font-size: 0.78rem;
    letter-spacing: 0.04em;
}
.tq-footer a { color: rgba(77,217,255,0.5); text-decoration: none; }
.tq-footer a:hover { color: #4dd9ff; }

/* ── DIVIDER ── */
hr {
    border: none !important;
    border-top: 1px solid rgba(255,255,255,0.06) !important;
    margin: 28px 0 !important;
}

/* streamlit column gaps */
[data-testid="column"] { padding: 0 12px !important; }
[data-testid="column"]:first-child { padding-left: 0 !important; }
[data-testid="column"]:last-child { padding-right: 0 !important; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource(show_spinner="Cargando Knowledge Base...")
def load_system():
    return TQKnowledgeSystem()

system = load_system()

# ── HERO ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <div class="hero-inner">
    <div class="hero-eyebrow"><span></span>Asistente Virtual Corporativo</div>
    <h1>TQ <em>Confiable</em></h1>
    <p class="hero-sub">
      Tecnoquimicas S.A. &mdash; Mas de 90 años liderando la industria farmaceutica y de consumo<br>
      en Colombia y America Latina con productos Totalmente Confiables
    </p>
    <div class="hero-stats">
      <div class="hero-stat"><strong>90+</strong><span>Años de trayectoria</span></div>
      <div class="hero-divider"></div>
      <div class="hero-stat"><strong>8.200+</strong><span>Colaboradores</span></div>
      <div class="hero-divider"></div>
      <div class="hero-stat"><strong>20+</strong><span>Paises</span></div>
      <div class="hero-divider"></div>
      <div class="hero-stat"><strong>4.000+</strong><span>Referencias</span></div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── MAIN CONTENT ──────────────────────────────────────────────────────────────
st.markdown('<div class="main-wrap">', unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs([
    "Preguntas y Respuestas",
    "Resumen Ejecutivo",
    "FAQ Automatico",
    "Arquitectura",
])

EXAMPLES = [
    "Cuando fue fundada Tecnoquimicas?",
    "Cuales son todas las marcas de TQ?",
    "Que es la marca MK y en que paises esta?",
    "En que paises opera Tecnoquimicas?",
    "Que hace TQ por el medio ambiente?",
    "Que beneficios tienen los empleados?",
    "Como aplicar a una vacante en TQ?",
    "Cuantos colaboradores tiene TQ?",
    "Que estudios respaldan los productos TQ?",
    "Que es el programa Nuestros Hijos a la U?",
    "Como contacto a Tecnoquimicas?",
    "Que es la linea etica de TQ?",
]

# ── TAB 1: Q&A ────────────────────────────────────────────────────────────────
with tab1:
    st.markdown('<p class="section-title">Consulta al Asistente</p>', unsafe_allow_html=True)
    st.markdown('<p class="</p>', unsafe_allow_html=True)

    col_main, col_ex = st.columns([3, 1], gap="large")

    with col_ex:
        st.markdown('<p class="examples-label">Preguntas de ejemplo</p>', unsafe_allow_html=True)
        for ex in EXAMPLES:
            st.markdown('<div class="example-btn">', unsafe_allow_html=True)
            if st.button(ex, key=f"ex_{ex[:25]}"):
                st.session_state["q"] = ex
            st.markdown('</div>', unsafe_allow_html=True)

    with col_main:
        question = st.text_area(
            "PREGUNTA",
            value=st.session_state.get("q", ""),
            placeholder="Escribe tu pregunta sobre Tecnoquimicas...",
            height=110,
            key="q",
            label_visibility="visible",
        )

        c1, c2 = st.columns([3, 1], gap="small")
        with c1:
            ask = st.button("Preguntar", type="primary", use_container_width=True)
        with c2:
            if st.button("Limpiar", type="secondary", use_container_width=True):
                st.session_state["q"] = ""
                st.session_state["ans"] = ""
                st.rerun()

        if ask and question.strip():
            with st.spinner("Consultando la Knowledge Base..."):
                st.session_state["ans"] = system.answer_question(question)

        ans = st.session_state.get("ans", "")
        if ans:
            st.markdown(f"""
            <div class="answer-wrap">
              <div class="answer-label">Respuesta — TQ-Bot</div>
              <div class="answer-text">{ans}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="answer-wrap">
              <div class="answer-label">Respuesta — TQ-Bot</div>
              <div class="answer-placeholder">La respuesta aparecera aqui una vez hagas una pregunta...</div>
            </div>
            """, unsafe_allow_html=True)

# ── TAB 2: RESUMEN ────────────────────────────────────────────────────────────
with tab2:
    st.markdown('<p class="section-title">Resumen Ejecutivo</p>', unsafe_allow_html=True)
    st.markdown('<p class="section-sub">Generado por Gemini 2.5 Flash a partir de la Knowledge Base real de Tecnoquimicas.</p>', unsafe_allow_html=True)

    if st.button("Generar Resumen Ejecutivo", type="primary"):
        with st.spinner("Generando resumen con Gemini 2.5 Flash..."):
            st.session_state["summary"] = system.get_summary()

    if "summary" in st.session_state and st.session_state["summary"]:
        st.markdown(st.session_state["summary"])

# ── TAB 3: FAQ ────────────────────────────────────────────────────────────────
with tab3:
    st.markdown('<p class="section-title">Preguntas Frecuentes</p>', unsafe_allow_html=True)
    st.markdown('<p class="section-sub">10 preguntas frecuentes generadas automaticamente por IA desde la Knowledge Base.</p>', unsafe_allow_html=True)

    if st.button("Generar FAQ", type="primary"):
        with st.spinner("Analizando Knowledge Base con Gemini 2.5 Flash..."):
            st.session_state["faq"] = system.get_faq()

    if "faq" in st.session_state and st.session_state["faq"]:
        st.markdown(st.session_state["faq"])

# ── TAB 4: ARQUITECTURA ───────────────────────────────────────────────────────
with tab4:
    st.markdown('<p class="section-title">Arquitectura del Sistema</p>', unsafe_allow_html=True)
    st.markdown('<p class="section-sub">Diseno tecnico, tecnologias y metricas del sistema Q&A semantico.</p>', unsafe_allow_html=True)

    col_a, col_b = st.columns([3, 2], gap="large")

    with col_a:
        st.markdown("##### Tecnologias")
        st.markdown("""
| Componente | Tecnologia |
|---|---|
| **LLM** | Google Gemini 2.5 Flash |
| **Framework** | LangChain |
| **Web Scraping** | Selenium + Chrome + BeautifulSoup4 |
| **Interfaz** | Streamlit |
| **Empresa** | Tecnoquimicas S.A. (TQ Confiable) |
        """)

        st.markdown("##### Flujo del Sistema")
        st.code("""
www.tqconfiable.com  (12 URLs verificadas)
        |
   scraper.py    ->   raw_data.json
   Selenium          JS renderizado
        |
knowledge_base.py -> knowledge_base.txt
Limpieza+Chunking    chunks.json
        |
  qa_system.py  (Gemini 2.5 Flash + LangChain)
   |        |        |
Resumen    FAQ    Q&A Contextual
        |
    app.py  ->  Streamlit UI
""", language="text")

        st.markdown("##### Prompt Engineering")
        st.markdown("""
- **Tecnica:** Zero-shot con contexto completo en system prompt
- **Anti-alucinacion:** El modelo responde solo con datos del contexto
- **Temperatura:** 0.1 — maxima precision y coherencia
- **Grounding:** Instruccion explicita de responder no se antes de inventar
        """)

    with col_b:
        st.markdown("##### Metricas de la Knowledge Base")
        st.markdown("""
<div class="metric-grid">
  <div class="metric-card">
    <div class="metric-num">48.630</div>
    <div class="metric-desc">Caracteres en la<br>Knowledge Base</div>
  </div>
  <div class="metric-card">
    <div class="metric-num">72</div>
    <div class="metric-desc">Chunks semanticos<br>generados</div>
  </div>
  <div class="metric-card">
    <div class="metric-num">12</div>
    <div class="metric-desc">URLs scrapeadas<br>de tqconfiable.com</div>
  </div>
  <div class="metric-card">
    <div class="metric-num">11/12</div>
    <div class="metric-desc">Paginas con<br>contenido exitoso</div>
  </div>
</div>
        """, unsafe_allow_html=True)

        st.markdown("##### Datos reales extraidos")
        st.markdown("""
- Historia 1934 - 2020 (18.579 chars)
- 8.200+ colaboradores, 8 sedes productivas
- Marcas: MK, Winny, Content, Sal de Frutas LUA, Noraver, Ibuflash, Duraflex, Yodora, CureBand, Hidraplus
- Paises: Colombia, Ecuador, El Salvador, Guatemala, Honduras, Nicaragua, Panama, Costa Rica, Rep. Dominicana, +20 exportaciones
- 400+ quimicos, 647 estudios cientificos (1998-2024)
- 36.000 paneles solares, PTAR propias, 100% reciclaje
        """)

st.markdown('</div>', unsafe_allow_html=True)

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="tq-footer">
  TQ Confiable &mdash; Sistema Q&A Semantico &nbsp;&bull;&nbsp;
  <a href="https://www.tqconfiable.com" target="_blank">tqconfiable.com</a>
  &nbsp;&bull;&nbsp; Taller 1 &mdash; Técnicas Avanzadas de IA Aplicadas En Modelos De Lenguaje
</div>
""", unsafe_allow_html=True)
