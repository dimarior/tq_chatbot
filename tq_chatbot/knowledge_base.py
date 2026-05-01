"""
knowledge_base.py
Limpia, consolida y fragmenta (chunking) el texto extraido de
tqconfiable.com y tqfarma.com
Genera: knowledge_base.txt y chunks.json
Ejecutar: python knowledge_base.py
"""

import re
import json
from pathlib import Path
from datetime import datetime

# Aumenta el CHUNK_SIZE para que la IA lea bloques más grandes de una vez
CHUNK_SIZE = 1500  
CHUNK_OVERLAP = 300 

NAV_SKIP = {
    "Síguenos", "LinkedIn", "Instagram", "Facebook", "Youtube", "Twitter",
    "Colaborador TQ", "Portal Médicos", "Encuéntranos", "Gobierno Corporativo",
    "Así Cambiamos El Mundo", "Trabaja con Nosotros", "Nuestras Marcas",
    "Noticias", "Contacto", "Inicio", "Términos y condiciones",
    "Políticas de privacidad", "Todos los derechos reservados",
    "MK", "Winny", "Sal de Frutas Lua", "Gastrofast", "Duraflex",
    "Ibuflash", "Yodora", "INICIAR SESIÓN", "REGISTRARSE",
    "Vademécum", "Biblioteca científica", "Medicamentos A-Z",
    "Inicio Biblioteca", "Acceso a Journals", "VER TODAS", "ACCEDER",
    "Volver", "Aceptar", "Enviar", "Comparte en:"
}

# La "Lista Negra" para eliminar la basura de los formularios y pop-ups (Frases largas)
BASURA_PHRASES = [
    "Usted está siendo redirigido", "sitio web externo y ajeno",
    "Si desea continuar, haga clic", "Bienvenido al Chat",
    "Tipo de identificación", "Cédula de", "Carnet diplomático",
    "ID extranjero", "Fideicomiso", "Registro civil", "Tarjeta de identidad",
    "El usuario tiene que ser de", "El correo solo puede", 
    "El teléfono solo puede", "Acepto los Términos", "var metaTag",
    "return metaTag", "No description found"
]

# Lista para palabras sueltas (solo borra si la línea es EXACTAMENTE esto)
EXACT_BASURA = {
    "Nacionalidad", "Nombre", "Apellidos", "Correo Electrónico", 
    "Teléfono", "Enviar", "Colombia", "Venezuela", "Ecuador", "Pasaporte"
}

# Orden de prioridad de secciones en la Knowledge Base
ORDER_PRIORITY = [
    "quien_es_tq", "proposito", "mision", "vision", "credo", "historia",
    "planeta", "gente", "innovacion", "investigacion",
    "beneficios", "ofertas", "testimonios",
    "encuentranos", "servicio", "faq", "linea_etica", "gobierno",
    "tqfarma_quienes", "tqfarma_inicio", "tqfarma_vademecum",
    "tqfarma_vademecum_mk", "tqfarma_vademecum_otc",
    "tqfarma_medicamentos", "tqfarma_noticias", "tqfarma_guias",
    "tqfarma_contacto", "noticias",
    "noticia_alcohol_gel", "noticia_multilatinas", "noticia_lactancia",
    "noticia_500empresas", "noticia_historia_medicina", "noticia_winny_marca",
    "noticia_copidrogas", "noticia_educacion", "noticia_canguro",
    "noticia_ecuador", "noticia_asocoldro", "noticia_asinfar",
    "noticia_ced_graduacion", "noticia_codigo_etica", "noticia_andi_barberi",
    "noticia_auditorio", "noticia_winny_prematuros", "noticia_colbon",
    "noticia_educando", "noticia_vive_tq", "noticia_reputacion",
    "noticia_cruz_roja", "noticia_proveedor_lider", "noticia_estudio_salutia",
    "noticia_dermatologicos", "noticia_cultura", "noticia_valle_lili",
    "noticia_winny_innovador", "noticia_compromiso", "noticia_tq_agro",
    "noticia_vacunacion", "noticia_orden_merito", "noticia_cancer_colon",
    "noticia_educacion_calidad", "noticia_grupo_innovacion",
    "noticia_comunidad", "noticia_content",
]


def clean_text(text: str) -> str:
    lines = text.splitlines()
    filtered = []
    for line in lines:
        line = line.strip()
        
        # Filtro 1: Exacto (para palabras sueltas de formularios/menús)
        if line in EXACT_BASURA or line in NAV_SKIP:
            continue
            
        # Filtro 2: Si es muy corta y no tiene números (fechas/años), descartar
        if not (len(line) >= 3 or (len(line) > 0 and any(c.isdigit() for c in line))):
            continue
            
        # Filtro 3: Parcial (para frases largas del bot/popups)
        if any(basura in line for basura in BASURA_PHRASES):
            continue
            
        filtered.append(line)
    return '\n'.join(filtered)

def build_chunks(text: str) -> list[str]:
    paragraphs = [p.strip() for p in text.split('\n\n') if len(p.strip()) > 10]
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= 1200:
            current += ('\n\n' if current else '') + para
        else:
            if current:
                chunks.append(current)
                current = para
    if current:
        chunks.append(current)
    return chunks


def build_knowledge_base(raw_data: dict) -> tuple[str, list[dict]]:
    print("\n" + "=" * 65)
    print("  CONSTRUYENDO KNOWLEDGE BASE - TQ CONFIABLE")
    print(f"  Secciones disponibles en raw_data: {len(raw_data)}")
    print(f"  Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    remaining = [k for k in raw_data if k not in ORDER_PRIORITY]
    final_order = ORDER_PRIORITY + remaining

    full_parts = []
    all_chunks = []
    chunk_id = 0
    procesadas = 0
    omitidas = 0

    print()
    for section in final_order:
        if section not in raw_data:
            continue

        cleaned = clean_text(raw_data[section])

        if len(cleaned.strip()) < 50:
            omitidas += 1
            continue

        full_parts.append(cleaned)
        section_chunks = build_chunks(cleaned)
        procesadas += 1

        for chunk_text in section_chunks:
            all_chunks.append({
                "id": chunk_id,
                "section": section,
                "source": "tqfarma.com" if section.startswith("tqfarma") else "tqconfiable.com",
                "text": chunk_text,
                "length": len(chunk_text),
            })
            chunk_id += 1

        chars = len(cleaned)
        status = "tqfarma.com" if section.startswith("tqfarma") else "tqconfiable.com"
        print(f"  ✅ {section:<40} {len(section_chunks):2} chunks | {chars:>7,} chars | {status}")

    full_text = "\n\n".join(full_parts)

    Path("knowledge_base.txt").write_text(full_text, encoding="utf-8")
    Path("chunks.json").write_text(
        json.dumps(all_chunks, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    tqconfiable_chunks = sum(1 for c in all_chunks if c["source"] == "tqconfiable.com")
    tqfarma_chunks     = sum(1 for c in all_chunks if c["source"] == "tqfarma.com")
    tqconfiable_chars  = sum(c["length"] for c in all_chunks if c["source"] == "tqconfiable.com")
    tqfarma_chars      = sum(c["length"] for c in all_chunks if c["source"] == "tqfarma.com")

    print(f"\n{'='*65}")
    print(f"  KNOWLEDGE BASE CONSTRUIDA LIMPIA Y PURGADA")
    print(f"{'='*65}")
    print(f"  Secciones procesadas : {procesadas}")
    print(f"  Secciones omitidas   : {omitidas}")
    print(f"  Total chunks         : {len(all_chunks)}")
    print(f"  Total caracteres     : {len(full_text):,}")
    print(f"{'='*65}\n")

    return full_text, all_chunks


if __name__ == "__main__":
    kb_path = Path("raw_data.json")
    if not kb_path.exists():
        print("❌ No se encontró raw_data.json")
    else:
        with open(kb_path, encoding="utf-8") as f:
            raw = json.load(f)
        build_knowledge_base(raw)
