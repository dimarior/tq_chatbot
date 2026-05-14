"""
structured_tool.py
Herramienta de recuperacion determinista sobre datos estructurados de TQ.

A diferencia del RAG (busqueda semantica sobre documentos), esta herramienta
retorna datos exactos y verificados: telefono, horario, NIT, sedes, marcas, etc.
No usa embeddings ni base vectorial — es una busqueda por palabras clave sobre
un JSON fijo. Esto garantiza precision del 100% para datos de contacto concretos.

Uso:
    from apps.api.tools.structured_tool import get_structured_data, needs_structured_tool
"""
from __future__ import annotations

import json
from pathlib import Path

# Carga el JSON una sola vez al importar el modulo (evita I/O repetido)
_DATA_PATH = Path(__file__).parent.parent / "datos_estructurados.json"
DATA: dict = json.loads(_DATA_PATH.read_text(encoding="utf-8"))

# Palabras clave que indican que la pregunta es mejor respondida con datos
# estructurados que con busqueda semantica sobre documentos
STRUCTURED_KEYWORDS: list[str] = [
    # Contacto
    "telefono", "teléfono", "llamar", "numero", "número", "celular",
    "email", "correo", "mail", "escribir",
    # Horario
    "horario", "hora", "atienden", "abierto", "atencion", "atención",
    "cuando atienden", "cuándo atienden",
    # Identificacion
    "nit", "razón social", "razon social", "rut",
    # Ubicacion
    "sede", "dirección", "direccion", "ubicacion", "ubicación",
    "dónde", "donde", "oficina", "planta",
    # Marcas y productos
    "marcas", "productos", "portafolio", "catalogo", "catálogo",
    # Empleo
    "trabaja", "empleo", "vacante", "oferta", "trabajo",
    # Linea etica
    "etica", "ética", "denuncia", "linea etica", "línea ética",
]


def needs_structured_tool(question: str) -> bool:
    """
    Decide si la pregunta debe enrutarse a la herramienta estructurada.
    Retorna True si la pregunta contiene palabras clave de datos concretos.
    El router del agente usa esta funcion antes de decidir si hacer RAG.
    """
    q = question.lower()
    return any(kw in q for kw in STRUCTURED_KEYWORDS)


def get_structured_data(question: str) -> str:
    """
    Recupera datos exactos de Tecnoquimicas segun la intencion de la pregunta.
    Retorna un string en espanol listo para ser usado como respuesta directa
    o como contexto adicional para el LLM.

    Esta funcion NO usa el LLM ni embeddings — es recuperacion determinista.
    """
    q = question.lower()

    # ── Telefono / contacto ──────────────────────────────────────────────────
    if any(w in q for w in ["telefono", "teléfono", "llamar", "numero", "número"]):
        c = DATA["contacto"]
        return (
            f"Línea de Servicio al Cliente: {c['telefono_cliente']}\n"
            f"Línea Ética: {c['linea_etica']}\n"
            f"Horario: {c['horario_atencion']}"
        )

    # ── Email ────────────────────────────────────────────────────────────────
    if any(w in q for w in ["email", "correo", "mail", "escribir"]):
        c = DATA["contacto"]
        return (
            f"Correo de servicio al cliente: {c['email_cliente']}\n"
            f"Sitio web: {c['sitio_web']}\n"
            f"Portal médico: {c['portal_medico']}"
        )

    # ── Horario ──────────────────────────────────────────────────────────────
    if any(w in q for w in ["horario", "hora", "atienden", "abierto", "atencion", "atención"]):
        return f"Horario de atención: {DATA['contacto']['horario_atencion']}"

    # ── NIT / identificacion ─────────────────────────────────────────────────
    if any(w in q for w in ["nit", "razón social", "razon social"]):
        e = DATA["empresa"]
        return (
            f"Razón social: {e['nombre']}\n"
            f"NIT: {e['nit']}\n"
            f"Nombre comercial: {e['nombre_comercial']}"
        )

    # ── Sedes / ubicacion ────────────────────────────────────────────────────
    if any(w in q for w in ["sede", "dirección", "direccion", "ubicacion", "ubicación",
                             "dónde", "donde", "oficina", "planta"]):
        sedes = DATA["sedes"]
        result = "Sedes de Tecnoquímicas:\n"
        for key, sede in sedes.items():
            result += f"• {sede['ciudad']} ({sede['departamento']}): {sede.get('direccion', sede.get('descripcion', ''))}\n"
        return result.strip()

    # ── Marcas ───────────────────────────────────────────────────────────────
    if any(w in q for w in ["marcas", "portafolio", "catalogo", "catálogo"]):
        marcas = ", ".join(DATA["marcas"])
        return f"Marcas de Tecnoquímicas: {marcas}"

    # ── Lineas de negocio ────────────────────────────────────────────────────
    if any(w in q for w in ["productos", "lineas", "líneas", "negocio"]):
        lineas = "\n".join(f"• {l}" for l in DATA["lineas_negocio"])
        return f"Líneas de negocio de Tecnoquímicas:\n{lineas}"

    # ── Empleo ───────────────────────────────────────────────────────────────
    if any(w in q for w in ["trabaja", "empleo", "vacante", "oferta", "trabajo"]):
        emp = DATA["empleo"]
        return (
            f"Portal de empleo: {emp['portal_ofertas']}\n"
            f"Programa de beneficios: {emp['programa_beneficios']}\n"
            f"Programa universitarios: {emp['programa_universitarios']}"
        )

    # ── Linea etica ──────────────────────────────────────────────────────────
    if any(w in q for w in ["etica", "ética", "denuncia", "linea etica", "línea ética"]):
        return (
            f"Línea Ética TQ: {DATA['contacto']['linea_etica']}\n"
            f"Disponible 24/7 para reportar situaciones que afecten la integridad corporativa."
        )

    # ── Datos generales de la empresa ────────────────────────────────────────
    e = DATA["empresa"]
    return (
        f"Tecnoquímicas S.A. (TQ Confiable)\n"
        f"NIT: {e['nit']} | Fundada: {e['fundacion']}\n"
        f"Colaboradores: {e['colaboradores']} | Países: {e['paises_presencia']}\n"
        f"Teléfono: {DATA['contacto']['telefono_cliente']}\n"
        f"Sitio web: {DATA['contacto']['sitio_web']}"
    )
