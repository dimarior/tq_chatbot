"""Fetch every URL listed in the sitemaps of tqconfiable.com and tqfarma.com.

Pipeline (per --site):
  1. Download sitemap.xml via `webclaw <url> --raw-html` (TLS fingerprinting;
     httpx gets blocked at the SSL handshake by tqconfiable's WAF).
  2. Parse <loc> entries; canonicalize known hosts (force https://www).
  3. For each URL, invoke `webclaw <url> --format json` in a thread pool
     (--concurrency workers). Each worker writes its data/raw/<sha1>.json
     immediately on completion — progress is visible in real time.
  4. Idempotent: skip writes when content_hash matches the existing JSON.

Requires the `webclaw` binary on PATH:
    brew install 0xMassi/webclaw/webclaw

Run from project root:
    uv run python scripts/fetch_sitemaps.py --site all
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree as ET

# Ejecutable como script (`python scripts/fetch_sitemaps.py`) o importable como
# módulo: asegura la raíz del repo en sys.path para resolver `scripts.*`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.tqfarma_news import build_news_text, is_tqfarma_login_page, parse_tqfarma_news


LOG = logging.getLogger("fetch_sitemaps")

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
FAILED_LOG = RAW_DIR / "_failed.log"

WEBCLAW_BIN = os.environ.get("WEBCLAW_BIN", "webclaw")
WEBCLAW_TIMEOUT = int(os.environ.get("WEBCLAW_TIMEOUT", "30"))

SITEMAPS = {
    "tqconfiable": "https://www.tqconfiable.com/sitemap.xml",
    "tqfarma": "https://www.tqfarma.com/sitemap.xml",
}

# Flags de webclaw por sitio para extraer SOLO el contenido útil. Sin esto,
# el markdown trae header, sidebar, menús, "Lo más leído", "Regístrese al
# portal", etc — el mismo boilerplate aparece en cientos de docs y rompe el
# RAG (embeddings casi idénticos). --only-main-content selecciona el bloque
# principal (article/main heurístico) y descarta chrome del sitio.
EXTRACTION_FLAGS = {
    "tqfarma": ("--only-main-content",),
    "tqconfiable": ("--only-main-content",),
}

# tqfarma exige login de profesional de la salud para 1700+ URLs del sitemap;
# los productos redirigen a /Account/Login. Estas pocas URLs son públicas con
# contenido sustantivo y se procesan siempre. Para tqfarma, además de esta
# lista se recorre el sitemap completo: la mayoría de esas URLs se descartan en
# _process_one (login wall), pero las "Noticias de actualidad" exponen un
# resumen público que la rama tqfarma de _process_one extrae. Ver
# scripts/tqfarma_news.py.
PUBLIC_URL_OVERRIDES: dict[str, list[str]] = {
    "tqfarma": [
        "https://www.tqfarma.com/",
        "https://www.tqfarma.com/quienes-somos",
        "https://www.tqfarma.com/contactenos",
        "https://www.tqfarma.com/vademecum/",
        "https://www.tqfarma.com/medicamentos-a-z",
        "https://www.tqfarma.com/biblioteca-cientifica",
        "https://www.tqfarma.com/biblioteca-cientifica/cursos-online/",
        "https://www.tqfarma.com/biblioteca-cientifica/noticias-actualidad/",
    ],
}

# Páginas índice cuyos enlaces internos directos también son públicos. Para cada
# (index_url, regex), el script descarga el HTML y añade al override las rutas
# que matchean. Solo páginas listado (un nivel), no los artículos individuales
# detrás de "ver más" — esos en su mayoría son gated.
PUBLIC_URL_DISCOVERY: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "tqfarma": [
        (
            "https://www.tqfarma.com/biblioteca-cientifica/noticias-actualidad/",
            re.compile(r'href="(/biblioteca-cientifica/noticias-actualidad/[a-z0-9-]+/?)"'),
        ),
    ],
}

# tqconfiable's sitemap lists http://www.tqconfiable.com/* URLs but the server
# only answers on https://www.tqconfiable.com/*. Force the canonical host+scheme
# for known domains so webclaw doesn't waste time on TCP timeouts.
CANONICAL_HOSTS = {
    "tqconfiable.com": "https://www.tqconfiable.com",
    "www.tqconfiable.com": "https://www.tqconfiable.com",
    "tqfarma.com": "https://www.tqfarma.com",
    "www.tqfarma.com": "https://www.tqfarma.com",
}


@dataclass
class FetchResult:
    url: str
    source: str
    status: str  # 'fetched' | 'skipped' | 'failed'
    reason: str = ""


def _slug(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonicalize(url: str) -> str:
    parts = urlsplit(url)
    base = CANONICAL_HOSTS.get(parts.netloc.lower())
    if not base:
        return url
    new_base = urlsplit(base)
    return urlunsplit((new_base.scheme, new_base.netloc, parts.path, parts.query, parts.fragment))


def _check_webclaw() -> None:
    if not shutil.which(WEBCLAW_BIN):
        LOG.error("`%s` not found on PATH.", WEBCLAW_BIN)
        LOG.error("install it with: brew install 0xMassi/webclaw/webclaw")
        LOG.error("(or set WEBCLAW_BIN to a custom path)")
        sys.exit(2)
    try:
        subprocess.run([WEBCLAW_BIN, "--version"], check=True, capture_output=True, timeout=10)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        LOG.error("webclaw is installed but does not run cleanly: %s", e)
        sys.exit(2)


def _webclaw_run(url: str, *extra: str) -> bytes:
    proc = subprocess.run(
        [WEBCLAW_BIN, url, *extra, "--timeout", str(WEBCLAW_TIMEOUT)],
        check=True,
        capture_output=True,
        timeout=WEBCLAW_TIMEOUT + 10,
    )
    return proc.stdout


def _webclaw_extract(url: str, source: str) -> dict:
    extra = EXTRACTION_FLAGS.get(source, ())
    return json.loads(_webclaw_run(url, "--format", "json", "--browser", "chrome", *extra))


def _webclaw_raw(url: str) -> bytes:
    """Fetch raw bytes — TLS fingerprinting bypasses WAFs that block httpx."""
    return _webclaw_run(url, "--raw-html")


def _source_of(url: str) -> str | None:
    netloc = urlsplit(url).netloc.lower()
    for src in SITEMAPS:
        if src in netloc:
            return src
    return None


def _read_failed_urls() -> dict[str, list[str]]:
    if not FAILED_LOG.exists():
        return {}
    grouped: dict[str, list[str]] = {}
    for line in FAILED_LOG.read_text("utf-8").splitlines():
        url = line.split("\t", 1)[0].strip()
        if not url:
            continue
        src = _source_of(url)
        if src is None:
            LOG.warning("retry: skipping unknown host %s", url)
            continue
        grouped.setdefault(src, []).append(url)
    return grouped


def _discover_extras(source: str) -> list[str]:
    """Expand each (index, regex) pair into the canonical child URLs it links to.

    Used for sites in PUBLIC_URL_OVERRIDES that also have index pages (e.g.
    /biblioteca-cientifica/noticias-actualidad/) where the list of public
    children grows over time and we don't want to hardcode every specialty.
    """
    rules = PUBLIC_URL_DISCOVERY.get(source, [])
    discovered: list[str] = []
    seen: set[str] = set()
    for index_url, pattern in rules:
        try:
            html = _webclaw_raw(index_url).decode("utf-8", "replace")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            LOG.warning("discovery failed for %s: %s", index_url, e)
            continue
        base = urlsplit(index_url)
        origin = f"{base.scheme}://{base.netloc}"
        for path in pattern.findall(html):
            full = _canonicalize(origin + path)
            if full not in seen:
                seen.add(full)
                discovered.append(full)
    return discovered


def _parse_sitemap(sitemap_url: str) -> list[str]:
    raw = _webclaw_raw(sitemap_url)
    root = ET.fromstring(raw)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    if root.tag.endswith("sitemapindex"):
        urls: list[str] = []
        for sm in root.findall("sm:sitemap/sm:loc", ns):
            urls.extend(_parse_sitemap(sm.text.strip()))
        return urls
    return [_canonicalize(loc.text.strip()) for loc in root.findall("sm:url/sm:loc", ns) if loc.text]


_write_lock = threading.Lock()


def _try_tqfarma_news(url: str, force: bool) -> FetchResult | None:
    """Rama exclusiva de tqfarma: detecta una página "Noticias de actualidad"
    con resumen público y escribe un payload limpio (título/especialidad/
    fecha/resumen).

    Devuelve un FetchResult cuando la página ES una noticia de ese tipo
    (fetched/skipped); devuelve None cuando NO lo es — y entonces _process_one
    sigue por la ruta normal, dejando intacta cualquier otra página de tqfarma.
    """
    try:
        html = _webclaw_raw(url).decode("utf-8", "replace")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None  # falló el raw fetch → que la ruta normal lo intente/reporte

    parsed = parse_tqfarma_news(html, fallback_url=url)
    if parsed is None:
        # Página gated: el raw HTML ya es el login. No hace falta una segunda
        # llamada a webclaw (--format json) para confirmar el login wall.
        if is_tqfarma_login_page(html):
            return FetchResult(url, "tqfarma", "failed", "login wall")
        return None

    # La URL canónica (og:url) puede diferir de la del sitemap (alias cortos).
    # Indexamos siempre por la canónica para no duplicar documentos.
    canonical = parsed["canonical_url"]
    text = build_news_text(parsed)
    content_hash = _hash(text)
    out_path = RAW_DIR / f"{_slug(canonical)}.json"

    if not force:
        try:
            existing = json.loads(out_path.read_text("utf-8"))
            if existing.get("content_hash") == content_hash:
                return FetchResult(canonical, "tqfarma", "skipped", "hash unchanged")
        except FileNotFoundError:
            pass
        except (json.JSONDecodeError, OSError):
            pass  # corrupt file → re-fetch

    payload = {
        "url": canonical,
        "source": "tqfarma",
        "title": parsed["title"],
        "text": text,
        "content_hash": content_hash,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    with _write_lock:
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    return FetchResult(canonical, "tqfarma", "fetched", "news summary")


def _process_one(url: str, source: str, force: bool) -> FetchResult:
    # tqfarma-only: las "Noticias de actualidad" devuelven HTTP 200 con un
    # resumen público (no redirigen a login). Se detectan y parsean aquí; si la
    # página no es una noticia de ese tipo, se cae a la ruta normal de abajo.
    if source == "tqfarma":
        news = _try_tqfarma_news(url, force)
        if news is not None:
            return news

    out_path = RAW_DIR / f"{_slug(url)}.json"

    try:
        wc = _webclaw_extract(url, source)
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        msg = stderr[-1] if stderr else f"exit {e.returncode}"
        return FetchResult(url, source, "failed", f"webclaw: {msg}")
    except subprocess.TimeoutExpired:
        return FetchResult(url, source, "failed", f"timeout>{WEBCLAW_TIMEOUT + 10}s")
    except json.JSONDecodeError as e:
        return FetchResult(url, source, "failed", f"json parse: {e}")
    except Exception as e:
        return FetchResult(url, source, "failed", f"{type(e).__name__}: {e}")

    metadata = wc.get("metadata") or {}
    content = wc.get("content") or {}
    text = (content.get("markdown") or "").strip()
    if len(text) < 50:
        return FetchResult(url, source, "failed", f"empty content (len={len(text)})")

    # tqfarma redirige URLs gated a /Account/Login?regresar=... — webclaw
    # entrega el HTML del login en vez del contenido pedido. Detectarlo aquí
    # evita meter formularios de login en el RAG aunque la allowlist falle.
    final_url = (metadata.get("url") or "").lower()
    if "/account/login" in final_url:
        return FetchResult(url, source, "failed", "login wall")

    content_hash = _hash(text)
    title = metadata.get("title")

    if not force:
        try:
            existing = json.loads(out_path.read_text("utf-8"))
            if existing.get("content_hash") == content_hash:
                return FetchResult(url, source, "skipped", "hash unchanged")
        except FileNotFoundError:
            pass
        except (json.JSONDecodeError, OSError):
            pass  # corrupt file → re-fetch

    payload = {
        "url": url,
        "source": source,
        "title": title,
        "text": text,
        "content_hash": content_hash,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    with _write_lock:
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    return FetchResult(url, source, "fetched")


def _process_site(source: str, urls: list[str], force: bool, concurrency: int) -> list[FetchResult]:
    results: list[FetchResult] = []
    counts = {"fetched": 0, "skipped": 0, "failed": 0}
    total = len(urls)
    progress_every = max(1, total // 50)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_process_one, u, source, force): u for u in urls}
        for i, fut in enumerate(as_completed(futures), start=1):
            r = fut.result()
            results.append(r)
            counts[r.status] += 1
            if r.status == "failed":
                LOG.warning("[%s] %d/%d FAIL %s — %s", source, i, total, r.url, r.reason)
            elif i == 1 or i == total or i % progress_every == 0:
                LOG.info(
                    "[%s] %d/%d (fetched=%d skipped=%d failed=%d) last=%s",
                    source, i, total, counts["fetched"], counts["skipped"], counts["failed"], r.url,
                )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", choices=["all", *SITEMAPS.keys()], default="all")
    parser.add_argument("--force", action="store_true", help="ignore content_hash skip")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="process only first N urls per site (0 = all)")
    parser.add_argument("--retry-failed", action="store_true", help="retry only URLs from data/raw/_failed.log (no sitemap fetch)")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    _check_webclaw()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    all_results: list[FetchResult] = []

    if args.retry_failed:
        grouped = _read_failed_urls()
        if args.site != "all":
            grouped = {args.site: grouped.get(args.site, [])}
        if not any(grouped.values()):
            LOG.info("no failed urls to retry")
            return 0
        for source, urls in grouped.items():
            if not urls:
                continue
            if args.limit > 0:
                urls = urls[: args.limit]
            LOG.info("retry %s -> %d urls", source, len(urls))
            all_results.extend(_process_site(source, urls, args.force, args.concurrency))
    else:
        sites = list(SITEMAPS.items()) if args.site == "all" else [(args.site, SITEMAPS[args.site])]
        for source, sm_url in sites:
            override = PUBLIC_URL_OVERRIDES.get(source)
            if override:
                # dedupe preserving order: overrides explícitos, luego descubiertos,
                # luego el sitemap completo. Los overrides/descubiertos conservan su
                # comportamiento exacto; las URLs del sitemap que no sean noticias
                # caen a la ruta normal en _process_one y se descartan igual que hoy.
                urls = list(override)
                seen: set[str] = set(urls)
                n_explicit = len(urls)

                for u in _discover_extras(source):
                    if u not in seen:
                        urls.append(u)
                        seen.add(u)
                n_discovered = len(urls) - n_explicit

                try:
                    sitemap_urls = _parse_sitemap(sm_url)
                except Exception as e:
                    LOG.error("sitemap parse failed for %s: %s", source, e)
                    sitemap_urls = []
                for u in sitemap_urls:
                    if u not in seen:
                        urls.append(u)
                        seen.add(u)
                n_sitemap = len(urls) - n_explicit - n_discovered

                LOG.info(
                    "%s -> %d urls (%d explicit + %d discovered + %d sitemap)",
                    source, len(urls), n_explicit, n_discovered, n_sitemap,
                )
            else:
                try:
                    urls = _parse_sitemap(sm_url)
                except Exception as e:
                    LOG.error("sitemap parse failed for %s: %s", source, e)
                    continue
                LOG.info("sitemap %s -> %d urls", source, len(urls))
            if args.limit > 0:
                urls = urls[: args.limit]
                LOG.info("limit=%d: processing first %d urls for %s", args.limit, len(urls), source)
            all_results.extend(_process_site(source, urls, args.force, args.concurrency))

    fetched = sum(1 for r in all_results if r.status == "fetched")
    skipped = sum(1 for r in all_results if r.status == "skipped")
    failed = [r for r in all_results if r.status == "failed"]
    LOG.info("done: fetched=%d skipped=%d failed=%d", fetched, skipped, len(failed))
    if failed:
        FAILED_LOG.write_text(
            "\n".join(f"{r.url}\t{r.reason}" for r in failed) + "\n", "utf-8"
        )
        LOG.warning("failures written to %s", FAILED_LOG)
    elif FAILED_LOG.exists():
        FAILED_LOG.unlink()

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
