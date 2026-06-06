"""Operación y demostración del hand autónomo `collector-tq` de OpenFang.

El hand recibe ticks autónomos del daemon, pero su prompt genérico
("review shared memory for pending tasks") hace que qwen3:8b se detenga sin
arrancar el playbook de 7 fases. Este script cierra ese hueco con un prompt
EXPLÍCITO y acotado (openfang/hands/collector-tq/cycle_prompt.es.txt) por dos
vías que comparten el mismo prompt para no desincronizarse:

  - schedule : agenda un cron de OpenFang que dispara el ciclo solo (autonomía).
  - trigger  : dispara un ciclo manual ahora (red de seguridad para la demo).

Y dos utilidades para la exposición:

  - status   : imprime la evidencia (grafo + métricas del dashboard + reporte).
  - reset    : limpia los artefactos para empezar la demo en cero.

El id del agente se resuelve por NOMBRE ("collector-tq-hand") vía REST, no se
hardcodea: reactivar el hand lo re-spawna con otro id (ver README del módulo).

Uso (desde la raíz del repo):
    uv run python scripts/collector_demo.py trigger
    uv run python scripts/collector_demo.py schedule [--every "*/15 * * * *"]
    uv run python scripts/collector_demo.py unschedule
    uv run python scripts/collector_demo.py status
    uv run python scripts/collector_demo.py reset [--yes]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CYCLE_PROMPT = ROOT / "openfang" / "hands" / "collector-tq" / "cycle_prompt.es.txt"
REPORT_GLOB = "collector_tq_report*.md"

OPENFANG_URL = os.environ.get("OPENFANG_URL", "http://127.0.0.1:4200").rstrip("/")
OPENFANG_DB = Path(
    os.environ.get("OPENFANG_DB", "~/.openfang/data/openfang.db")
).expanduser()
OPENFANG_BIN = os.environ.get("OPENFANG_BIN", "openfang")

AGENT_NAME = "collector-tq-hand"
# El tool file_write del hand escribe en su workspace sandbox, no en el cwd.
WORKSPACE = Path(
    os.environ.get("OPENFANG_WORKSPACES", "~/.openfang/workspaces")
).expanduser() / AGENT_NAME
CRON_NAME = "collector-tq-cycle"
# Cron de demo: cada 15 min para que dispare en vivo durante una exposición.
# Para producción usa algo como "0 8 * * *" (diario 8am).
DEFAULT_SPEC = "*/15 * * * *"

# Claves de métricas del dashboard (deben coincidir con [dashboard] del HAND.toml).
METRIC_KEYS = (
    "collector_tq_data_points",
    "collector_tq_entities_tracked",
    "collector_tq_reports_generated",
    "collector_tq_last_update",
)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _die(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def resolve_agent_id() -> str:
    """Devuelve el id del agente del hand, buscándolo por nombre vía REST."""
    try:
        r = httpx.get(f"{OPENFANG_URL}/api/agents", timeout=10)
        r.raise_for_status()
    except httpx.HTTPError as e:
        _die(f"no pude hablar con el daemon de OpenFang en {OPENFANG_URL} ({e}).\n"
             "¿está arriba? -> `make of-start`")
    for a in r.json():
        if a.get("name") == AGENT_NAME:
            return a["id"]
    _die(f"no encuentro el agente '{AGENT_NAME}'. ¿activaste el hand? -> `make of-hand`")


def _db() -> sqlite3.Connection:
    if not OPENFANG_DB.exists():
        _die(f"no existe la BD de OpenFang: {OPENFANG_DB}. Arranca el daemon: `make of-start`")
    conn = sqlite3.connect(str(OPENFANG_DB), timeout=10.0)
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def _decode_kv(value) -> str:
    """El kv_store guarda BLOB JSON-encoded; lo dejamos legible."""
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", "replace")
    try:
        return json.dumps(json.loads(value), ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        return str(value)


def _etype(raw) -> str:
    """El entity_type viene como JSON envuelto, p.ej. {"custom":"producto"} o
    una variante string. Lo dejamos en una etiqueta legible."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return str(raw)
    if isinstance(parsed, dict):
        return str(next(iter(parsed.values()), raw))
    return str(parsed)


def _read_prompt() -> str:
    if not CYCLE_PROMPT.exists():
        _die(f"falta el prompt de ciclo: {CYCLE_PROMPT}")
    return CYCLE_PROMPT.read_text("utf-8").strip()


def _of(*args: str) -> subprocess.CompletedProcess:
    """Corre el binario de openfang y devuelve el proceso (texto capturado)."""
    return subprocess.run(
        [OPENFANG_BIN, *args], capture_output=True, text=True, check=False
    )


# ── Comandos ──────────────────────────────────────────────────────────────────
def cmd_trigger(args: argparse.Namespace) -> int:
    agent_id = resolve_agent_id()
    prompt = _read_prompt()
    print(f"→ disparando un ciclo en {AGENT_NAME} ({agent_id[:8]}…). "
          f"qwen3:8b es lento; esto puede tardar ~1-2 min…")
    try:
        r = httpx.post(
            f"{OPENFANG_URL}/api/agents/{agent_id}/message",
            json={"message": prompt},
            timeout=args.timeout,
        )
        r.raise_for_status()
    except httpx.TimeoutException:
        print("⏱  el cliente expiró, pero el daemon puede seguir trabajando.\n"
              "    Revisa el resultado con: make of-collector-status")
        return 0
    except httpx.HTTPError as e:
        _die(f"el daemon devolvió error: {e}")
    data = r.json()
    print(f"✓ ciclo terminado — iteraciones={data.get('iterations','?')} "
          f"in={data.get('input_tokens','?')} out={data.get('output_tokens','?')}")
    if data.get("response"):
        print(f"\nrespuesta del agente:\n{data['response']}")
    print("\nVerifica los artefactos con: make of-collector-status")
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    prompt = _read_prompt()
    # `cron create` exige el UUID (su --help miente con "name or ID") y además
    # sale con código 0 aunque falle, escribiendo "Failed"/"Invalid" a stdout.
    agent_id = resolve_agent_id()
    # Idempotente: si ya existe el cron con nuestro nombre, lo quitamos antes.
    _delete_our_crons(quiet=True)
    proc = _of("cron", "create", agent_id, args.every, prompt, "--name", CRON_NAME)
    # OpenFang 0.6.9 imprime "✘ Failed: ?" de forma espuria aunque el job se cree,
    # y sale con código 0 cuando de verdad falla. La única señal fiable es si el
    # job aparece luego en `cron list`.
    if not _our_cron_ids():
        out = (proc.stdout or "") + (proc.stderr or "")
        _die(f"`openfang cron create` no registró el job:\n{out.strip()}")
    print(f"✓ cron '{CRON_NAME}' creado: spec='{args.every}' → agente {AGENT_NAME} ({agent_id[:8]}…)")
    print("  el collector ahora ejecuta su ciclo SOLO según ese horario.")
    print("\nVerifica con: openfang cron list")
    return 0


def _our_cron_ids() -> list[str]:
    proc = _of("cron", "list")
    if proc.returncode != 0:
        return []
    try:
        jobs = json.loads(proc.stdout).get("jobs", [])
    except json.JSONDecodeError:
        return []
    return [j["id"] for j in jobs if j.get("name") == CRON_NAME]


def _delete_our_crons(quiet: bool = False) -> int:
    ids = _our_cron_ids()
    for jid in ids:
        _of("cron", "delete", jid)
    if ids and not quiet:
        print(f"✓ eliminados {len(ids)} cron(s) '{CRON_NAME}'")
    return len(ids)


def cmd_unschedule(args: argparse.Namespace) -> int:
    n = _delete_our_crons()
    if not n:
        print(f"no había crons '{CRON_NAME}' que borrar.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    conn = _db()
    try:
        ents = conn.execute(
            "SELECT entity_type, name FROM entities ORDER BY created_at DESC LIMIT 25"
        ).fetchall()
        n_ents = conn.execute("SELECT count(*) FROM entities").fetchone()[0]
        rels = conn.execute(
            "SELECT relation_type, source_entity, target_entity FROM relations "
            "ORDER BY created_at DESC LIMIT 15"
        ).fetchall()
        n_rels = conn.execute("SELECT count(*) FROM relations").fetchone()[0]
        metrics = dict(conn.execute(
            "SELECT key, value FROM kv_store WHERE key LIKE 'collector_tq%'"
        ).fetchall())
        events = conn.execute(
            "SELECT timestamp, target FROM events ORDER BY timestamp DESC LIMIT 5"
        ).fetchall()
    finally:
        conn.close()

    print("══ Collector TQ — evidencia ══════════════════════════════════════")
    print(f"\n● Métricas del dashboard ({len([k for k in METRIC_KEYS if k in metrics])}/4 puestas):")
    for k in METRIC_KEYS:
        val = _decode_kv(metrics[k]) if k in metrics else "—"
        print(f"    {k:32} {val}")

    print(f"\n● Grafo de conocimiento: {n_ents} entidades, {n_rels} relaciones")
    for etype, name in ents:
        print(f"    [{_etype(etype)}] {name}")
    if rels:
        print("  relaciones:")
        for rtype, src, tgt in rels:
            print(f"    {src} —{_etype(rtype)}→ {tgt}")

    print(f"\n● Eventos/alertas publicados: {len(events)}")
    for ts, tgt in events:
        print(f"    {ts}  → {tgt}")

    reports = sorted(WORKSPACE.glob(REPORT_GLOB)) if WORKSPACE.exists() else []
    print(f"\n● Reportes generados (archivos): {len(reports)}")
    for rp in reports:
        print(f"    {rp}  ({rp.stat().st_size} bytes)")

    if not n_ents and not any(k in metrics for k in METRIC_KEYS):
        print("\n⚠  Todo en cero: el collector aún no ha corrido un ciclo.\n"
              "   Dispara uno con: make of-collect   (o agenda: make of-schedule)")
    print("\nDashboard visual: openfang dashboard  →  http://127.0.0.1:4200")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    if not args.yes:
        ans = input("Esto BORRA el grafo (entities/relations), las métricas del "
                    "collector y los reportes. ¿Seguir? [y/N] ")
        if ans.strip().lower() not in ("y", "yes", "s", "si", "sí"):
            print("cancelado.")
            return 0
    conn = _db()
    try:
        # entities/relations no tienen agent_id en el esquema; hoy sólo el
        # collector las puebla, así que el wipe es global (documentado).
        n_e = conn.execute("DELETE FROM entities").rowcount
        n_r = conn.execute("DELETE FROM relations").rowcount
        n_k = conn.execute(
            "DELETE FROM kv_store WHERE key LIKE 'collector_tq%'"
        ).rowcount
        conn.commit()
    finally:
        conn.close()
    n_f = 0
    if WORKSPACE.exists():
        for rp in WORKSPACE.glob(REPORT_GLOB):
            rp.unlink()
            n_f += 1
    print(f"✓ reset: {n_e} entidades, {n_r} relaciones, {n_k} métricas, {n_f} reportes borrados.")
    print("  (el grafo es global en OpenFang; sólo el collector lo puebla)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("trigger", help="dispara un ciclo manual ahora")
    t.add_argument("--timeout", type=float, default=300.0, help="timeout HTTP en segundos")
    t.set_defaults(func=cmd_trigger)

    s = sub.add_parser("schedule", help="agenda el ciclo con un cron de OpenFang")
    s.add_argument("--every", default=DEFAULT_SPEC, help=f'cron spec (default "{DEFAULT_SPEC}")')
    s.set_defaults(func=cmd_schedule)

    u = sub.add_parser("unschedule", help="borra el cron del collector")
    u.set_defaults(func=cmd_unschedule)

    st = sub.add_parser("status", help="imprime la evidencia (grafo + métricas + reportes)")
    st.set_defaults(func=cmd_status)

    r = sub.add_parser("reset", help="limpia los artefactos del collector")
    r.add_argument("--yes", action="store_true", help="no pidas confirmación")
    r.set_defaults(func=cmd_reset)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
