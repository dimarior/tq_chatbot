"""
qa_system.py
Sistema Q&A con Google Gemini + LangChain.
La API Key se carga desde el archivo .env

DONDE VA LA API KEY:
  Crea un archivo llamado .env en la misma carpeta con este contenido:
      GOOGLE_API_KEY=AIzaSy_TU_CLAVE_AQUI
  Obtén tu clave gratis en: https://aistudio.google.com/app/apikey
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Carga GOOGLE_API_KEY desde el archivo .env
load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


def get_llm() -> ChatGoogleGenerativeAI:
    #api_key = os.getenv("GOOGLE_API_KEY")
    try:
        import streamlit as st
        api_key = st.secrets["GOOGLE_API_KEY"]
    except Exception:
        api_key = os.getenv("GOOGLE_API_KEY")
    
    if not api_key:
        raise EnvironmentError(
            "\n No se encontró GOOGLE_API_KEY.\n"
            "   Crea el archivo .env con:\n"
            "       GOOGLE_API_KEY=tu_clave_aqui\n"
            "   Obtén tu clave gratis en: https://aistudio.google.com/app/apikey\n"
        )
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key,
        temperature=0.1,
        max_output_tokens=8192,
    )


def load_knowledge_base() -> str:
    kb_path = Path(__file__).parent / "knowledge_base.txt"
    if not kb_path.exists():
        raise FileNotFoundError(
            "\n No se encontró knowledge_base.txt\n"
            "   Ejecuta en orden:\n"
            "       1. python scraper.py\n"
            "       2. python knowledge_base.py\n"
        )
    return kb_path.read_text(encoding="utf-8")[:15000]


# ── PROMPT 1: Resumen Ejecutivo ───────────────────────────────────────────────
SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Eres un analista corporativo experto. Genera un resumen ejecutivo
profesional de Tecnoquimicas (TQ Confiable) basandote UNICAMENTE en el contexto.

REGLAS:
- Usa SOLO informacion del contexto. Nunca inventes datos.
- Estructura: Quienes somos, Historia, Marcas, Presencia geografica, Innovacion, Sostenibilidad, Empleo.
- Tono profesional. Extension: 350-450 palabras.
- Si un dato no esta en el contexto, no lo incluyas.

CONTEXTO:
{knowledge_base}"""),
    ("human", "Genera el resumen ejecutivo de Tecnoquimicas S.A."),
])

# ── PROMPT 2: FAQ Automatico ──────────────────────────────────────────────────
FAQ_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Eres experto en comunicacion corporativa. Analiza el contexto de
Tecnoquimicas y genera exactamente 10 Preguntas Frecuentes con sus respuestas.

REGLAS:
- Cada respuesta debe basarse UNICAMENTE en el contexto.
- Si no tienes informacion suficiente, responde: "Para mas informacion visita www.tqconfiable.com"
- Cubre estos temas: historia, productos/marcas, presencia geografica, empleo,
  sostenibilidad, beneficios colaboradores, contacto, innovacion.
- Formato exacto:
  Q1: [pregunta]
  A1: [respuesta]

CONTEXTO:
{knowledge_base}"""),
    ("human", "Genera las 10 preguntas frecuentes mas relevantes sobre Tecnoquimicas."),
])

# ── PROMPT 3: Q&A Contextual ──────────────────────────────────────────────────
QA_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Eres TQ-Bot, el asistente virtual oficial de Tecnoquimicas (TQ Confiable),
empresa colombiana lider en salud y bienestar con mas de 90 anos de trayectoria,
con sede principal en Cali, Valle del Cauca.

INSTRUCCIONES CRITICAS:
1. Responde UNICAMENTE con informacion del CONTEXTO DE CONOCIMIENTO.
2. Si la pregunta no se puede responder con el contexto, di exactamente:
   "No tengo esa informacion en mi base de conocimiento actual.
    Para mas detalles visita www.tqconfiable.com"
3. NUNCA inventes datos, cifras, nombres ni hechos que no esten en el contexto.
4. Responde en espanol, con tono amable y profesional.
5. Se conciso y directo. Maximo 3 parrafos.

CONTEXTO DE CONOCIMIENTO:
{knowledge_base}
---"""),
    ("human", "{question}"),
])


class TQKnowledgeSystem:
    """Sistema de conocimiento semantico para Tecnoquimicas S.A."""

    def __init__(self):
        self.llm = get_llm()
        self.knowledge_base = load_knowledge_base()
        self.parser = StrOutputParser()
        self.summary_chain = SUMMARY_PROMPT | self.llm | self.parser
        self.faq_chain     = FAQ_PROMPT     | self.llm | self.parser
        self.qa_chain      = QA_PROMPT      | self.llm | self.parser

    def get_summary(self) -> str:
        return self.summary_chain.invoke({"knowledge_base": self.knowledge_base})

    def get_faq(self) -> str:
        return self.faq_chain.invoke({"knowledge_base": self.knowledge_base})

    def answer_question(self, question: str) -> str:
        if not question or len(question.strip()) < 3:
            return "Por favor escribe una pregunta valida."
        return self.qa_chain.invoke({
            "knowledge_base": self.knowledge_base,
            "question": question.strip(),
        })