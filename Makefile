# Quickstart sin Docker. Sólo Ollama tiene que correr aparte (host).

# ── Instalación ──────────────────────────────
install:
	uv sync
	cd frontend && pnpm install

# ── Desarrollo (backend + frontend, dos procesos) ─────────────────
dev: backend frontend

# ── Solo backend ──────────────────────────────
backend:
	uv run uvicorn apps.api.main:app --reload --port 8000

# ── Solo frontend ─────────────────────────────
frontend:
	cd frontend && pnpm dev

# ── Ingesta del corpus a Chroma ───────────────
ingest:
	uv run python scripts/ingest_to_rag.py

# ── Reset total (borra SQLite + Chroma; el corpus en data/raw se conserva)
reset:
	rm -f tq.db tq.db-shm tq.db-wal
	rm -rf chroma_db

# ── Limpiar cache ─────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
