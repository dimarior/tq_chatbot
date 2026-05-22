# Quickstart sin Docker. Sólo Ollama tiene que correr aparte (host).

# OpenFang se instala en ~/.openfang/bin; make corre las recetas con /bin/sh
# (que NO lee ~/.zshrc) y a veces hace exec directo, así que resolvemos el
# binario explícitamente: lo busca en el PATH y si no cae al path del instalador.
OPENFANG := $(shell command -v openfang 2>/dev/null || echo $(HOME)/.openfang/bin/openfang)

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

# ═══════════════════════════════════════════════════════════════════════════
#  Módulo 3 — Ruta B: OpenFang Agent OS
#  Requiere: `curl -fsSL https://openfang.sh/install | sh` + Ollama corriendo.
#  Antes de of-start/of-migrate/of-whatsapp: copia openfang/.env.example a
#  openfang/.env y rellena el TELEGRAM_BOT_TOKEN.
# ═══════════════════════════════════════════════════════════════════════════
.PHONY: of-config of-start of-migrate of-hand of-whatsapp of-status of-doctor tsne

# Copia la config/agente/hand versionados a ~/.openfang (fuente de verdad = repo)
of-config:
	mkdir -p $$HOME/.openfang/agents $$HOME/.openfang/hands
	cp openfang/config.toml $$HOME/.openfang/config.toml
	cp -R openfang/agents/tq-asistente $$HOME/.openfang/agents/
	cp -R openfang/hands/collector-tq $$HOME/.openfang/hands/
	@echo "OK -> ~/.openfang (config + agente tq-asistente + hand collector-tq)"

# Arranca el daemon (dashboard en http://127.0.0.1:4200). Carga openfang/.env.
of-start:
	set -a; [ -f openfang/.env ] && . ./openfang/.env; set +a; $(OPENFANG) start

# Inyecta el conocimiento corporativo (KV vía REST + corpus al vector store)
of-migrate:
	set -a; [ -f openfang/.env ] && . ./openfang/.env; set +a; \
	uv run python scripts/migrate_to_openfang.py

# Activa el hand autónomo de inteligencia competitiva
of-hand:
	$(OPENFANG) hand activate collector-tq

# Arranca el gateway QR de WhatsApp (puerto 3009). OPENFANG_SRC = clon del repo OpenFang.
of-whatsapp:
	set -a; [ -f openfang/.env ] && . ./openfang/.env; set +a; \
	node "$${OPENFANG_SRC:-$$HOME/develop/openfang}/packages/whatsapp-gateway/index.js"

# Estado del daemon + de los hands activos
of-status:
	$(OPENFANG) status
	-$(OPENFANG) hand active

of-doctor:
	$(OPENFANG) doctor

# ── Bonus: análisis t-SNE/UMAP de intenciones ────────────────────────────────
tsne:
	uv run --group notebooks jupyter nbconvert --to notebook --execute \
	  --output intent_tsne.executed.ipynb notebooks/intent_tsne.ipynb
