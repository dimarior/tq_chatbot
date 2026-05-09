"""Truncate documents+chunks. Dev convenience; data/raw/ is preserved.

Run:
    uv run python scripts/reset_rag.py --yes
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import asyncpg

from apps.api.core.config import get_settings


async def main_async(yes: bool) -> int:
    if not yes:
        print("This wipes documents+chunks. Pass --yes to confirm.")
        return 1
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute("TRUNCATE chunks, documents RESTART IDENTITY CASCADE")
        print("RAG truncated.")
        return 0
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    return asyncio.run(main_async(args.yes))


if __name__ == "__main__":
    sys.exit(main())
