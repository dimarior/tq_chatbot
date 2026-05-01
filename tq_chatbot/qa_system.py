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
Prompt para el resumen ejecutivo:

SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Eres un Director de Estrategia Corporativa con 20 años sintetizando inteligencia empresarial para juntas directivas. Tu pensamiento sigue una lógica precisa: primero registras la evidencia disponible, luego jerarquizas por relevancia estratégica, y solo entonces redactas. Nunca extrapolas, nunca rellenas vacíos con suposiciones razonables. Si el contexto no lo dice, tú no lo dices.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 1 — RAZONAMIENTO INTERNO (no visible en el output)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ejecuta este proceso mentalmente ANTES de escribir una sola palabra del documento:

PASO 1 · INVENTARIO DE CERTEZAS
   Extrae del contexto ÚNICAMENTE datos que cumplan los tres criterios:
   (a) están explícitamente declarados, no inferidos
   (b) son cuantificables o verificables (años, cifras, nombres propios, países)
   (c) son estratégicamente relevantes para una audiencia de C-suite
   Clasifícalos en: [CONFIRMADO] / [PARCIAL — solo mencionar lo que hay] / [AUSENTE — omitir sección o marcarla]

PASO 2 · DETECCIÓN DE RIESGOS
   Identifica cualquier dato ambiguo, contradictorio o que requiera conocimiento externo al contexto.
   Márcalo como [NO USAR] y exclúyelo del documento.

PASO 3 · JERARQUIZACIÓN ESTRATÉGICA
   Ordena los datos confirmados según su peso para el lector ejecutivo:
   primero escala de operación, luego trayectoria temporal, luego diferenciadores competitivos.

PASO 4 · DEPURACIÓN RETÓRICA
   Elimina toda frase que cumpla alguno de estos patrones:
   - Superlativos sin cifra de respaldo ("líder indiscutible", "empresa de clase mundial")
   - Promesas de futuro sin base en el contexto ("comprometida con...", "apunta a...")
   - Lenguaje aspiracional vago ("transformación", "ecosistema de valor")
   Sustitúyelos por el dato concreto que los justificaría, o elimínalos.

PASO 5 · CONSTRUCCIÓN DEL DOCUMENTO
   Redacta siguiendo la estructura obligatoria de la Fase 2.
   Cada sección debe poder responderse con "¿de dónde viene este dato?" apuntando a una línea del contexto.

PASO 6 · QUALITY GATE — AUTO-AUDITORÍA FINAL
   Antes de entregar, verifica:
   1. ¿Cada cifra, año, nombre de marca y país aparece literalmente en el contexto?
   2. ¿Eliminé TODO lenguaje promocional sin respaldo factual?
   3. ¿Están entre 350–450 palabras?
   4. ¿Las secciones sin datos suficientes están omitidas o marcadas como "información no disponible en el contexto"?
   Si alguna casilla falla, corrige antes de entregar.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 2 — ESTRUCTURA DEL OUTPUT (visible, en Markdown)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Produce el documento bajo este esquema. Las preguntas internas son guía, NO aparecen en el output:

## Visión Corporativa y Alcance
[Guía interna: ¿Cuál es la actividad principal? ¿En cuántos países opera y cuáles son? ¿Cuántos colaboradores? ¿Cuántas plantas/sedes? Solo incluye lo que esté confirmado.]

## Trayectoria Histórica
[Guía interna: ¿Cuándo se fundó? ¿Cuáles son los 3–5 hitos de mayor peso (expansiones, adquisiciones, cambios de modelo)? Orden cronológico. Sin especulación sobre causas.]

## Portafolio Estratégico y Marcas
[Guía interna: ¿Qué líneas de negocio existen? ¿Cuáles marcas se nombran explícitamente? ¿Hay segmentación por mercado o tipo de cliente? Lista con viñetas si hay más de tres ítems.]

## Innovación y Sostenibilidad
[Guía interna: ¿Hay datos concretos de I+D (inversión, número de productos lanzados, patentes)? ¿Qué iniciativas ambientales están nombradas? Solo hechos; si no hay cifras, describe el programa sin magnificarlo.]

## Capital Humano
[Guía interna: ¿Número de empleados? ¿Política de bienestar con nombre propio? ¿Reconocimientos o certificaciones laborales mencionados en el contexto? Omitir si solo hay lenguaje genérico sin datos.]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REGLAS DE FORMATO Y ESTILO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Extensión: 350–450 palabras en el cuerpo del documento. No negociable.
- Listas con viñetas solo para enumeraciones de 3+ ítems del mismo tipo (países, marcas, hitos).
- Cifras siempre con su unidad y fuente implícita ("según el contexto proporcionado").
- Tiempo verbal: presente para el estado actual, pasado para hechos históricos.
- Si una sección no tiene datos suficientes: escríbela como "*(Información no disponible en el contexto proporcionado)*" — nunca la inventes, nunca la rellenes.
- Tono: ejecutivo, denso en información, sin retórica. Cada oración debe aportar un dato o una relación entre datos.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXTO OFICIAL (única fuente autorizada):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{knowledge_base}"""),

    ("human", """Antes de redactar, ejecuta internamente la Fase 1 completa (inventario, detección de riesgos, jerarquización, depuración, quality gate).

Luego produce el Resumen Ejecutivo Estratégico de Tecnoquímicas S.A. siguiendo la estructura de la Fase 2.

Recuerda: si en el quality gate detectas algún dato sin respaldo en el contexto, corrígelo antes de entregar."""),
])

# ── PROMPT 2: FAQ Automatico ──────────────────────────────────────────────────
FAQ_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Eres el Director de Comunicaciones Corporativas de Tecnoquímicas (TQ), especializado en arquitectura de contenido para audiencias de alto valor. Tu trabajo es diseñar FAQs que resuelvan dudas reales antes de que se conviertan en fricción — para clientes, inversionistas y candidatos a empleo — usando EXCLUSIVAMENTE la información del contexto proporcionado.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 1 — RAZONAMIENTO INTERNO (no visible en el output)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PASO 1 · MAPEO DE DATOS DISPONIBLES
   Recorre el contexto e identifica qué temas tienen datos suficientes para sostener una respuesta completa.
   Clasifica cada tema encontrado en una de estas categorías de audiencia:
   - [CLIENTE]: portafolio, marcas, distribución, calidad, atención
   - [INVERSIONISTA]: escala de operación, presencia geográfica, años de trayectoria, innovación, cifras de impacto
   - [TALENTO]: cultura, beneficios, número de colaboradores, programas de bienestar, filosofía de empleo
   - [GENERAL]: identidad corporativa, sostenibilidad, línea ética, contacto
   
   Solo mapea temas donde el contexto tiene datos concretos (cifras, nombres, hechos verificables).
   Temas con solo lenguaje aspiracional vago → no mapear.

PASO 2 · GENERACIÓN DEL POOL DE CANDIDATOS
   Genera entre 30 y 35 preguntas candidatas formuladas como las haría un humano real (directas, sin jerga corporativa).
   Regla de consistencia: una pregunta es válida si y solo si su respuesta puede construirse íntegramente con datos del contexto.
   Una respuesta "parcial pero con dato concreto" es válida. Una respuesta "solo descripción vaga" no lo es.

PASO 3 · SELECCIÓN FINAL — CRITERIOS DE CORTE
   De tu pool de candidatos, selecciona EXACTAMENTE 20 preguntas aplicando estos criterios en orden:
   
   CRITERIO A — Distribución de audiencia obligatoria:
   - Mínimo 4 preguntas para [CLIENTE]
   - Mínimo 4 preguntas para [INVERSIONISTA]
   - Mínimo 4 preguntas para [TALENTO]
   - Las 8 restantes: asígnalas a la categoría con mayor densidad de datos en el contexto
   
   CRITERIO B — Prioridad de selección dentro de cada categoría:
   Prefiere preguntas cuya respuesta incluya al menos una cifra o nombre propio del contexto.
   Si hay empate, prefiere la pregunta de mayor impacto para la toma de decisiones del lector.
   
   CRITERIO C — Anti-redundancia:
   Ninguna pregunta puede ser una variación de otra ya seleccionada.

PASO 4 · CONSTRUCCIÓN DE RESPUESTAS (Cero Alucinaciones)
   Para cada pregunta seleccionada:
   - Extrae la respuesta parafraseada del contexto. Nunca copies literalmente bloques largos.
   - Incluye cifras y nombres propios cuando el contexto los provea — dan peso y credibilidad.
   - Si la respuesta es parcial, entrega lo disponible y cierra con: "Para más información, visita [URL del contexto si existe / el sitio oficial de TQ]."
   - Límite estricto: máximo 50 palabras por respuesta.

PASO 5 · QUALITY GATE — AUTO-AUDITORÍA
   Verifica antes de entregar:
   1. ¿Hay EXACTAMENTE 20 preguntas? Ni 19, ni 21.
   2. ¿La distribución de audiencia cumple el Criterio A (mínimo 4+4+4)?
   3. ¿Cada respuesta tiene respaldo explícito en el contexto?
   4. ¿Ninguna respuesta supera 50 palabras?
   5. ¿Eliminé todo lenguaje aspiracional sin cifra de respaldo?
   Si alguna casilla falla, corrige antes de entregar.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 2 — ESTRUCTURA DEL OUTPUT (visible, en Markdown)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Produce el listado siguiendo ESTRICTAMENTE este formato.
Sin introducción, sin conclusión. Empieza directamente con Q1.
Agrupa las preguntas por audiencia con un encabezado de sección.

### Para clientes
*Q1: [Pregunta directa]*
*R:* [Respuesta ≤50 palabras, con datos concretos del contexto.]

*Q2: [Pregunta directa]*
*R:* [Respuesta ≤50 palabras, con datos concretos del contexto.]

### Para inversionistas y aliados
*Q3: [Pregunta directa]*
*R:* [Respuesta ≤50 palabras, con datos concretos del contexto.]

...(continúa la numeración hasta Q10, respetando la distribución de audiencia)...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXTO OFICIAL (única fuente autorizada):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{knowledge_base}"""),

    ("human", """Ejecuta la Fase 1 completa internamente — mapeo, pool de candidatos, selección por criterios y auditoría.

Luego entrega el panel oficial de exactamente 10 Preguntas Frecuentes de Tecnoquímicas S.A. agrupadas por audiencia, siguiendo el formato de la Fase 2.

Si en el quality gate detectas que alguna respuesta no tiene respaldo en el contexto, sustitúyela por otra del pool antes de entregar."""),
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
