# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Streamlit Q&A chatbot ("TQ-Confiable") about Tecnoquímicas S.A. Academic project (Taller 1 — Técnicas Avanzadas de IA Aplicadas en Modelos de Lenguaje). All user-facing copy and prompts are in Spanish — preserve language when editing.

## Layout note

The project root holds `pyproject.toml` / `uv.lock` / `main.py` (a stub), but the actual application lives one level down in `tq_chatbot/`. **All commands below must be run from `tq_chatbot/`**, not the repo root, because the scripts read/write files via relative paths (`raw_data.json`, `knowledge_base.txt`, `chunks.json`, `.env`).

`main.py` at the repo root is a placeholder and is not the entry point.

## Setup & commands

Python 3.14 (`.python-version`). Project metadata is managed with `uv` (root `pyproject.toml` + `uv.lock`), but the runtime scripts use plain `pip`-installable deps listed in `tq_chatbot/requirements.txt`.

```bash
# from tq_chatbot/
pip install -r requirements.txt          # or: uv sync from repo root
echo "GOOGLE_API_KEY=..." > .env         # required, see qa_system.py
```

Selenium auto-downloads ChromeDriver via `webdriver-manager`, but a local Chrome/Chromium install is required for the scraper.

### Pipeline (must run in order)

```bash
cd tq_chatbot
python scraper.py          # ~12 + 9 URLs → raw_data.json
python knowledge_base.py   # raw_data.json → knowledge_base.txt + chunks.json
python -m streamlit run app.py
```

`knowledge_base.py` will refuse to run if `raw_data.json` is missing; `qa_system.py` will refuse to start if `knowledge_base.txt` is missing. There are no tests, no linter, no build step.

### API key resolution

`qa_system.get_llm()` tries `st.secrets["GOOGLE_API_KEY"]` first (for Streamlit Cloud `.streamlit/secrets.toml` deployment), then falls back to the `GOOGLE_API_KEY` env var loaded from `tq_chatbot/.env` via `python-dotenv`. Keep both paths working when touching that function.

## Architecture

Linear file-based pipeline — no database, no vector store, no retrieval step.

```
tqconfiable.com (Selenium) ─┐
                             ├─► raw_data.json ─► knowledge_base.txt ─► qa_system ─► app.py (Streamlit, 4 tabs)
tqfarma.com   (requests)  ──┘                  └► chunks.json (unused)
```

### Stages

1. **`scraper.py`** — Two engines: Selenium + headless Chrome for `tqconfiable.com` (JS-rendered, anti-bot evasion via `navigator.webdriver` override and a real-looking UA), plain `requests` + BeautifulSoup for `tqfarma.com`. URLs are hardcoded in two dicts (`URLS_SELENIUM`, `URLS_REQUESTS`) — adding a page means editing one of those and adding the section key to `ORDER_PRIORITY` in `knowledge_base.py`. Output: `raw_data.json` keyed by section name.

2. **`knowledge_base.py`** — Cleans nav chrome, deduplicates lines, then concatenates sections in the order defined by `ORDER_PRIORITY` (corporate identity first, news last). Also produces `chunks.json` (paragraph-aware splits with `CHUNK_SIZE=800`, `CHUNK_OVERLAP=150`) — currently **emitted but not consumed**; the Q&A path uses the full text file, not the chunks. If you wire up retrieval, this is the file to read.

3. **`qa_system.py`** — `TQKnowledgeSystem` builds three LangChain chains (`SUMMARY_PROMPT | llm | parser`, same for `FAQ_PROMPT` and `QA_PROMPT`) over `gemini-2.5-flash` at `temperature=0.1`. The entire knowledge base (truncated to **15 000 chars** in `load_knowledge_base`) is injected into every system prompt — this is zero-shot grounding, not RAG. If the KB grows past that limit, either bump the slice or introduce real retrieval over `chunks.json`.

4. **`app.py`** — Single-file Streamlit UI with heavy custom CSS, four tabs (Q&A, Resumen Ejecutivo, FAQ, Arquitectura). `TQKnowledgeSystem` is built once via `@st.cache_resource`. Hero stats and the "Arquitectura" tab contain hard-coded numbers (8.200+ colaboradores, 48.630 chars, 72 chunks, etc.) that are not derived from the KB at runtime — update them by hand if the KB regenerates with materially different sizes.

### Prompt design (load-bearing)

The three prompts in `qa_system.py` are the product. They are intentionally elaborate Spanish prompts with explicit phases (internal reasoning → output structure → quality gate) and strict anti-hallucination rules:

- `SUMMARY_PROMPT` — 350–450-word executive brief, 5 fixed sections, must mark missing data as *"Información no disponible en el contexto proporcionado"* rather than invent.
- `FAQ_PROMPT` — exactly 20 (header says 20 but the human turn says 10 — both numbers exist in the file) Q&As distributed across CLIENTE / INVERSIONISTA / TALENTO audiences, ≤50 words per answer.
- `QA_PROMPT` — 4-protocol triage (TOTAL / PARCIAL / NULA / SENSIBLE) with safety templates for sensitive topics (recalls, litigation, health incidents) that must redirect to official TQ channels without confirming or denying.

When editing these prompts: keep the system/human split, keep `{knowledge_base}` and `{question}` placeholders intact, and don't translate them to English. Recent git history shows the team iterates on these files individually (`SUMMARY_PROMPT (update).py`, etc.) — they are the main thing that changes.

## Conventions

- Filenames, section keys, prompt content, and console banners are Spanish (often without accents in identifiers, with accents in user-facing text). Match existing style; don't introduce English identifiers.
- Section keys in `raw_data.json` are the contract between `scraper.py` and `knowledge_base.py`. New keys must be added to `ORDER_PRIORITY` or they get appended at the end.
- `tqfarma_*` prefix marks tqfarma.com sources — `knowledge_base.py` uses this prefix to tag chunk `source` metadata. Preserve the prefix when adding tqfarma URLs.
