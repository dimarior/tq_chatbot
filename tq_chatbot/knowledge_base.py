"""
knowledge_base.py
Limpia, consolida y fragmenta (chunking) el texto extraído de tqconfiable.com.
Genera: knowledge_base.txt y chunks.json
Ejecutar: python knowledge_base.py
"""

import re
import json
from pathlib import Path

CHUNK_SIZE    = 800
CHUNK_OVERLAP = 150

NAV_SKIP = {
    "Síguenos", "LinkedIn", "Instagram", "Facebook", "Youtube", "Twitter",
    "Colaborador TQ", "Portal Médicos", "Encuéntranos", "Gobierno Corporativo",
    "Así Cambiamos El Mundo", "Trabaja con Nosotros", "Nuestras Marcas",
    "Noticias", "Contacto", "Inicio", "Términos y condiciones",
    "Políticas de privacidad", "Todos los derechos reservados",
    "MK", "Winny", "Sal de Frutas Lua", "Gastrofast", "Duraflex",
    "Ibuflash", "Yodora",
}


def clean_text(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    lines = text.splitlines()
    filtered = []
    for line in lines:
        line = line.strip()
        if len(line) < 20:
            continue
        if line in NAV_SKIP:
            continue
        if re.match(r'^© \d{4}', line):
            continue
        filtered.append(line)
    return '\n'.join(filtered)


def build_chunks(text: str) -> list[str]:
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
    print("=" * 60)
    print("  CONSTRUYENDO KNOWLEDGE BASE - TQ CONFIABLE")
    print("=" * 60)

    ORDER = [
        "quienes_somos", "historia", "innovacion", "planeta",
        "beneficios", "marcas", "noticias", "trabaja",
        "contacto", "servicio", "faq", "linea_etica",
    ]

    full_parts = []
    all_chunks = []
    chunk_id = 0

    for section in ORDER:
        if section not in raw_data:
            continue
        cleaned = clean_text(raw_data[section])
        if len(cleaned.strip()) < 50:
            continue

        full_parts.append(cleaned)
        section_chunks = build_chunks(cleaned)

        for chunk_text in section_chunks:
            all_chunks.append({
                "id": chunk_id,
                "section": section,
                "text": chunk_text,
                "length": len(chunk_text),
            })
            chunk_id += 1

        print(f"   {section:20} → {len(section_chunks)} chunks")

    full_text = "\n\n" + ("=" * 60) + "\n\n".join(full_parts)

    Path("knowledge_base.txt").write_text(full_text, encoding="utf-8")
    Path("chunks.json").write_text(
        json.dumps(all_chunks, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n{'='*60}")
    print(f" knowledge_base.txt → {len(full_text):,} caracteres")
    print(f" chunks.json        → {len(all_chunks)} chunks")
    print(f"{'='*60}")
    return full_text, all_chunks


if __name__ == "__main__":
    kb_path = Path("raw_data.json")
    if not kb_path.exists():
        print(" No se encontró raw_data.json")
        print("   Ejecuta primero: python scraper.py")
    else:
        with open(kb_path, encoding="utf-8") as f:
            raw = json.load(f)
        build_knowledge_base(raw)