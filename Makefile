# ── Instalación ──────────────────────────────
install:
	uv sync
	cd frontend && pnpm install

# ── Desarrollo (levanta todo) ─────────────────
dev:
	docker compose up -d
	uv run uvicorn apps.api.main:app --reload --port 8000 &
	cd frontend && pnpm dev

# ── Solo backend ──────────────────────────────
backend:
	uv run uvicorn apps.api.main:app --reload --port 8000

# ── Solo frontend ─────────────────────────────
frontend:
	cd frontend && pnpm dev

# ── Base de datos ─────────────────────────────
db:
	docker compose up -d

# ── Limpiar cache ─────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete

# ── Ver logs ──────────────────────────────────
logs:
	docker compose logs -f