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

CHUNK_SIZE    = 800
CHUNK_OVERLAP = 150

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
}

# Orden de prioridad de secciones en la Knowledge Base
ORDER_PRIORITY = [
    # IDENTIDAD CORPORATIVA (mayor prioridad)
    "quien_es_tq", "proposito", "mision", "vision", "credo", "historia",
    # MUNDO
    "planeta", "gente",
    # INNOVACION
    "innovacion", "investigacion",
    # TRABAJA
    "beneficios", "ofertas", "testimonios",
    # CONTACTO
    "encuentranos", "servicio", "faq", "linea_etica",
    # GOBIERNO
    "gobierno",
    # TQFARMA (portal medico oficial)
    "tqfarma_quienes", "tqfarma_inicio", "tqfarma_vademecum",
    "tqfarma_vademecum_mk", "tqfarma_vademecum_otc",
    "tqfarma_medicamentos", "tqfarma_noticias", "tqfarma_guias",
    "tqfarma_contacto",
    # NOTICIAS (al final por ser contenido mas especifico)
    "noticias",
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
    """Limpieza profunda del texto crudo."""
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    lines = text.splitlines()
    filtered = []
    seen = set()
    for line in lines:
        line = line.strip()
        if len(line) < 15:
            continue
        if line in NAV_SKIP:
            continue
        if re.match(r'^© \d{4}', line):
            continue
        if re.match(r'^https?://', line):
            continue
        if line in seen:
            continue
        seen.add(line)
        filtered.append(line)
    return '\n'.join(filtered)


def build_chunks(text: str) -> list[str]:
    """Divide el texto en chunks semanticamente coherentes."""
    paragraphs = [p.strip() for p in text.split('\n\n') if len(p.strip()) > 30]
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= CHUNK_SIZE:
            current += ('\n\n' if current else '') + para
        else:
            if current:
                chunks.append(current)
                words = current.split()
                overlap = ' '.join(words[-(CHUNK_OVERLAP // 6):]) if len(words) > CHUNK_OVERLAP // 6 else ""
                current = (overlap + '\n\n' + para).strip() if overlap else para
            else:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                for sent in sentences:
                    if len(current) + len(sent) + 1 <= CHUNK_SIZE:
                        current += (' ' if current else '') + sent
                    else:
                        if current:
                            chunks.append(current)
                        current = sent

    if current:
        chunks.append(current)

    return [c for c in chunks if len(c.strip()) > 40]


def build_knowledge_base(raw_data: dict) -> tuple[str, list[dict]]:
    print("\n" + "=" * 65)
    print("  CONSTRUYENDO KNOWLEDGE BASE - TQ CONFIABLE")
    print(f"  Secciones disponibles en raw_data: {len(raw_data)}")
    print(f"  Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    # Construir orden final: primero las prioritarias, luego cualquier
    # seccion que este en raw_data pero no en ORDER_PRIORITY
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

    # Estadisticas por fuente
    tqconfiable_chunks = sum(1 for c in all_chunks if c["source"] == "tqconfiable.com")
    tqfarma_chunks     = sum(1 for c in all_chunks if c["source"] == "tqfarma.com")
    tqconfiable_chars  = sum(c["length"] for c in all_chunks if c["source"] == "tqconfiable.com")
    tqfarma_chars      = sum(c["length"] for c in all_chunks if c["source"] == "tqfarma.com")

    print(f"\n{'='*65}")
    print(f"  KNOWLEDGE BASE CONSTRUIDA")
    print(f"{'='*65}")
    print(f"  Secciones procesadas : {procesadas}")
    print(f"  Secciones omitidas   : {omitidas} (contenido insuficiente)")
    print(f"  Total chunks         : {len(all_chunks)}")
    print(f"  Total caracteres     : {len(full_text):,}")
    print()
    print(f"  Por fuente:")
    print(f"    tqconfiable.com    {tqconfiable_chunks:3} chunks | {tqconfiable_chars:>10,} chars")
    print(f"    tqfarma.com        {tqfarma_chunks:3} chunks | {tqfarma_chars:>10,} chars")
    print()
    print(f"  Archivos generados:")
    print(f"    knowledge_base.txt ({len(full_text):,} chars)")
    print(f"    chunks.json        ({len(all_chunks)} chunks con metadatos)")
    print(f"{'='*65}\n")

    return full_text, all_chunks


if __name__ == "__main__":
    kb_path = Path("raw_data.json")
    if not kb_path.exists():
        print("❌ No se encontró raw_data.json")
        print("   Ejecuta primero: python scraper.py")
    else:
        with open(kb_path, encoding="utf-8") as f:
            raw = json.load(f)
        build_knowledge_base(raw)
