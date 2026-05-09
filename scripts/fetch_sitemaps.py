"""Fetch every URL listed in the sitemaps of tqconfiable.com and tqfarma.com.

Pipeline per URL:
  1. Async GET via httpx (3 retries, exp backoff via tenacity).
  2. Parse with selectolax. If output is suspiciously short or page looks
     SPA-rendered, fallback to Playwright headless render.
  3. Normalize text, compute SHA-256 over normalized text.
  4. Skip write if data/raw/<sha1(url)>.json already has the same content_hash
     (idempotent re-runs).

Run from project root:
    uv run python scripts/fetch_sitemaps.py --site all
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx
from selectolax.parser import HTMLParser
from tenacity import AsyncRetrying, RetryError, retry_if_exception_type, stop_after_attempt, wait_exponential


LOG = logging.getLogger("fetch_sitemaps")

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
FAILED_LOG = RAW_DIR / "_failed.log"

SITEMAPS = {
    "tqconfiable": "https://tqconfiable.com/sitemap.xml",
    "tqfarma": "https://www.tqfarma.com/sitemap.xml",
}

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
SPA_MARKERS = ("__NEXT_DATA__", "data-reactroot", "ng-version", "id=\"__nuxt\"")


@dataclass
class FetchResult:
    url: str
    source: str
    status: str  # 'fetched' | 'skipped' | 'failed'
    reason: str = ""


def _slug(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def _normalize(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract(html: str) -> tuple[str | None, str]:
    tree = HTMLParser(html)
    title_node = tree.css_first("title")
    title = title_node.text(strip=True) if title_node else None
    for sel in ("nav", "header", "footer", "script", "style", "noscript", "form"):
        for n in tree.css(sel):
            n.decompose()
    main = tree.css_first("main") or tree.css_first("article") or tree.body
    text = main.text(separator=" ", strip=True) if main else ""
    return title, _normalize(text)


def _looks_spa(html: str, text: str) -> bool:
    if len(text) < 200:
        return True
    return any(m in html for m in SPA_MARKERS)


async def _fetch_via_playwright(url: str, timeout_s: int) -> tuple[str | None, str]:
    from playwright.async_api import async_playwright  # lazy import

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(user_agent=UA)
            page = await ctx.new_page()
            await page.goto(url, timeout=timeout_s * 1000, wait_until="networkidle")
            html = await page.content()
        finally:
            await browser.close()
    return _extract(html)


async def _fetch_via_http(client: httpx.AsyncClient, url: str) -> tuple[str | None, str, str]:
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPError,)),
        reraise=True,
    ):
        with attempt:
            r = await client.get(url, follow_redirects=True)
            r.raise_for_status()
            html = r.text
    title, text = _extract(html)
    return title, text, html


async def _parse_sitemap(client: httpx.AsyncClient, sitemap_url: str) -> list[str]:
    r = await client.get(sitemap_url, follow_redirects=True)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    # If it's a sitemap index, recursively expand.
    if root.tag.endswith("sitemapindex"):
        urls: list[str] = []
        for sm in root.findall("sm:sitemap/sm:loc", ns):
            urls.extend(await _parse_sitemap(client, sm.text.strip()))
        return urls
    return [loc.text.strip() for loc in root.findall("sm:url/sm:loc", ns) if loc.text]


async def _process_url(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    url: str,
    source: str,
    force: bool,
    timeout_s: int,
) -> FetchResult:
    out_path = RAW_DIR / f"{_slug(url)}.json"
    async with sem:
        try:
            try:
                title, text, html = await _fetch_via_http(client, url)
            except RetryError as e:
                return FetchResult(url, source, "failed", f"http: {e}")

            if _looks_spa(html, text):
                LOG.info("[playwright] %s", url)
                try:
                    title, text = await _fetch_via_playwright(url, timeout_s)
                except Exception as e:
                    return FetchResult(url, source, "failed", f"playwright: {e}")

            if len(text) < 50:
                return FetchResult(url, source, "failed", "empty content after extraction")

            content_hash = _hash(text)

            if not force and out_path.exists():
                try:
                    existing = json.loads(out_path.read_text("utf-8"))
                    if existing.get("content_hash") == content_hash:
                        return FetchResult(url, source, "skipped", "hash unchanged")
                except Exception:
                    pass

            payload = {
                "url": url,
                "source": source,
                "title": title,
                "text": text,
                "content_hash": content_hash,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
            return FetchResult(url, source, "fetched")
        except Exception as e:  # safety net
            return FetchResult(url, source, "failed", repr(e))


async def main_async(args: argparse.Namespace) -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    sites = list(SITEMAPS.items()) if args.site == "all" else [(args.site, SITEMAPS[args.site])]

    timeout = httpx.Timeout(connect=10.0, read=float(args.timeout), write=10.0, pool=10.0)
    headers = {"User-Agent": UA, "Accept-Language": "es-CO,es;q=0.9,en;q=0.7"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        # 1) collect URLs
        all_urls: list[tuple[str, str]] = []
        for source, sm_url in sites:
            try:
                urls = await _parse_sitemap(client, sm_url)
                LOG.info("sitemap %s -> %d urls", source, len(urls))
                all_urls.extend((source, u) for u in urls)
            except Exception as e:
                LOG.error("sitemap parse failed for %s: %s", source, e)

        # 2) fetch
        sem = asyncio.Semaphore(args.concurrency)
        tasks = [
            _process_url(client, sem, u, src, args.force, args.timeout)
            for src, u in all_urls
        ]
        results = await asyncio.gather(*tasks)

    fetched = sum(1 for r in results if r.status == "fetched")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = [r for r in results if r.status == "failed"]
    LOG.info("done: fetched=%d skipped=%d failed=%d", fetched, skipped, len(failed))
    if failed:
        FAILED_LOG.write_text(
            "\n".join(f"{r.url}\t{r.reason}" for r in failed) + "\n", "utf-8"
        )
        LOG.warning("failures written to %s", FAILED_LOG)

    return 0 if not failed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", choices=["all", *SITEMAPS.keys()], default="all")
    parser.add_argument("--force", action="store_true", help="ignore content_hash skip")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=20, help="per-request seconds")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
