"""Re-aplica el manifiesto de un agente preservando su memoria de OpenFang.

OpenFang NO actualiza el manifiesto en caliente: hay que DELETE + POST, lo que
crea un id nuevo y deja una sesión vacía. Este script automatiza el ciclo:
  1. Borra el agente actual (buscándolo por nombre).
  2. Lo recrea desde openfang/agents/<nombre>/agent.toml.
  3. Re-etiqueta sus memorias (corpus + hechos) del id viejo al nuevo.
  4. Re-siembra el KV store y las frases de hechos al id nuevo.

NOTA: la sesión de conversación se reinicia (es inevitable al recrear el agente).
Requiere el daemon corriendo (`openfang start`).

Uso:
    uv run python scripts/reload_agent.py [--agent tq-asistente]
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.migrate_to_openfang import (  # noqa: E402
    OPENFANG_DB,
    OPENFANG_URL,
    STRUCTURED_JSON,
    OpenFangMemoryClient,
    seed_facts,
    seed_structured_kv,
)

LOG = logging.getLogger("reload_agent")
ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agent", default="tq-asistente")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    manifest_path = ROOT / "openfang" / "agents" / args.agent / "agent.toml"
    if not manifest_path.exists():
        LOG.error("no encuentro el manifest: %s", manifest_path)
        return 1
    manifest = manifest_path.read_text("utf-8")

    try:
        with httpx.Client(base_url=OPENFANG_URL, timeout=30) as h:
            agents = h.get("/api/agents").raise_for_status().json()
            old = next((a["id"] for a in agents if a["name"] == args.agent), None)
            if old:
                h.request("DELETE", f"/api/agents/{old}").raise_for_status()
                LOG.info("agente '%s' borrado (id viejo=%s)", args.agent, old)
            new = h.post("/api/agents", json={"manifest_toml": manifest}).raise_for_status().json()["agent_id"]
            LOG.info("agente '%s' recreado (id nuevo=%s)", args.agent, new)

        if old:
            conn = sqlite3.connect(str(OPENFANG_DB), timeout=10.0)
            conn.execute("PRAGMA busy_timeout=5000;")
            n = conn.execute(
                "UPDATE memories SET agent_id = ? WHERE agent_id = ?", (new, old)
            ).rowcount
            conn.commit()
            conn.close()
            LOG.info("memorias re-etiquetadas al id nuevo: %d", n)
    except httpx.HTTPError as e:
        LOG.error("error de API de OpenFang: %s — ¿está corriendo `openfang start`?", e)
        return 1

    client = OpenFangMemoryClient(OPENFANG_URL, OPENFANG_DB)
    try:
        data = json.loads(STRUCTURED_JSON.read_text("utf-8"))
        seed_structured_kv(client, new, data, dry_run=False)
        with client.connection() as conn:
            seed_facts(conn, new, data, dry_run=False)
    finally:
        client.close()

    LOG.warning("la sesión de conversación se reinició (inevitable al recrear el agente)")
    LOG.info("recarga completada")
    return 0


if __name__ == "__main__":
    sys.exit(main())
