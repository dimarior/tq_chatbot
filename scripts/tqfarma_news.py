"""Detector y parser de páginas "Noticias de actualidad" de tqfarma.

tqfarma publica ~1600 noticias en el sitemap. El artículo completo exige login
de profesional de la salud, pero la página devuelve HTTP 200 con un resumen
público (título, especialidad, fecha, párrafo de entrada). Solo el enlace
"VER MÁS" está gated a /Account/Login.

Plantilla verificada (idéntica en varias especialidades):

    <h3 class="primary">Odontología</h3>          ← especialidad (subtítulo)
    <article ...>
      <header ...>
        <h1 ...>TÍTULO</h1>
        <small class="date">DD/MM/YYYY</small>
      </header>
      <div class="formatted"><p>RESUMEN…</p></div>
      <div class="box ...">
        <a href="/Account/Login?regresar=…">VER MÁS</a>   ← señal de gating
      </div>
    </article>

`parse_tqfarma_news(html)` devuelve un dict con los campos públicos cuando la
página coincide con esta plantilla, o None para cualquier otra cosa (muros de
login puros, páginas de producto, índices/listados, plantillas no-noticia). La
detección es puramente estructural: no depende de la forma de la URL.

Solo aplica a tqfarma — el llamador (fetch_sitemaps.py) la invoca únicamente
para ese source.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlsplit


# Marcador que viaja dentro del texto ingestado. El prompt del sistema lo
# reconoce para avisar al usuario que solo hay un resumen público y que el
# artículo completo requiere login. Ver apps/api/rag/prompt.py.
SUMMARY_MARKER = "[RESUMEN_PUBLICO_TQFARMA]"

_DATE_RE = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
_WS_RE = re.compile(r"\s+")

# Las URLs gated de tqfarma redirigen a /Account/Login; webclaw --raw-html
# entrega el HTML de esa página de login. Detectarlo por su og:url permite
# descartarlas sin una segunda llamada a webclaw. Las noticias nunca tienen
# este og:url (el suyo apunta a /noticias-actualidad/...).
_LOGIN_OG_URL_RE = re.compile(
    r"property=[\"']og:url[\"'][^>]*content=[\"'][^\"']*/account/login\b",
    re.IGNORECASE,
)

# Las páginas índice y de listado por especialidad embeben la noticia más
# reciente como un <article> destacado, estructuralmente idéntico a una página
# de detalle. El discriminador fiable es el path canónico (og:url): una noticia
# de detalle es .../noticias-actualidad/<especialidad>/<slug>; un listado se
# queda en .../noticias-actualidad/ o .../noticias-actualidad/<especialidad>.
_NEWS_PATH_RE = re.compile(
    r"^/biblioteca-cientifica/noticias-actualidad/[^/]+/[^/]+/?$", re.IGNORECASE
)

_VOID_TAGS = {
    "meta", "img", "br", "input", "source", "link", "hr",
    "area", "base", "col", "embed", "param", "track", "wbr",
}


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


class _NewsParser(HTMLParser):
    """Recorre el HTML una vez y acumula solo los campos públicos.

    Mantiene una pila de tags abiertos para saber, en cada `handle_data`, si el
    texto vive dentro de <article>, de su <h1>, de su <small class="date"> o de
    su <div class="formatted">. El <h1> del logo del sitio queda fuera porque no
    es descendiente de <article>.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict[str, str]]] = []
        self.og_url: str | None = None
        # subtítulo = último <h3 class="primary"> cerrado antes de abrir <article>
        self.subtitle: str | None = None
        self._h3_parts: list[str] = []
        self._article_started = False
        self.article_seen = False
        self.title_parts: list[str] = []
        self.date_parts: list[str] = []
        self.summary_parts: list[str] = []
        self.has_login_link = False

    def _has_ancestor(self, tag: str, cls_substr: str | None = None) -> bool:
        for t, attrs in self.stack:
            if t != tag:
                continue
            if cls_substr is None:
                return True
            if cls_substr in (attrs.get("class") or "").lower():
                return True
        return False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            if ad.get("property", "").lower() == "og:url" and ad.get("content"):
                self.og_url = ad["content"].strip()
            return
        if tag in _VOID_TAGS:
            return
        if tag == "article":
            self._article_started = True
        if tag == "a" and self._has_ancestor("article"):
            if "/account/login" in ad.get("href", "").lower():
                self.has_login_link = True
        self.stack.append((tag, ad))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # <meta .../> y otros void self-closing: delega; no se apila nada.
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        idx = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                idx = i
                break
        if idx is None:
            return
        popped_tag, popped_attrs = self.stack[idx]
        del self.stack[idx:]

        cls = (popped_attrs.get("class") or "").lower()
        if popped_tag == "h3" and "primary" in cls and not self._article_started:
            text = _norm("".join(self._h3_parts))
            if text:
                self.subtitle = text
            self._h3_parts = []
        elif popped_tag == "article":
            self.article_seen = True

    def handle_data(self, data: str) -> None:
        if not self._article_started and self._has_ancestor("h3", "primary"):
            self._h3_parts.append(data)
        if not self._has_ancestor("article"):
            return
        if self._has_ancestor("h1"):
            self.title_parts.append(data)
        if self._has_ancestor("small", "date"):
            self.date_parts.append(data)
        if self._has_ancestor("div", "formatted"):
            self.summary_parts.append(data)


def parse_tqfarma_news(html: str, fallback_url: str | None = None) -> dict | None:
    """Devuelve los campos públicos si `html` es una noticia tqfarma, o None.

    La firma estructural exigida (todas obligatorias):
      1. existe un <article>;
      2. dentro: un <h1> con texto y un <small class="date"> con DD/MM/YYYY;
      3. un <div class="formatted"> con resumen sustantivo (>= 40 chars);
      4. un enlace "VER MÁS" hacia /Account/Login (confirma que es la plantilla
         de noticia gated y que lo que tenemos es solo el resumen);
      5. el path canónico es el de una noticia de detalle, no un índice/listado
         (estos embeben la noticia más reciente con la misma estructura).

    Cualquier página que no cumpla las cinco devuelve None, y el llamador la
    procesa por la ruta normal sin cambios.
    """
    parser = _NewsParser()
    try:
        parser.feed(html)
    except Exception:
        return None

    if not parser.article_seen:
        return None

    canonical = parser.og_url or fallback_url
    if not canonical or not _NEWS_PATH_RE.match(urlsplit(canonical).path):
        return None

    title = _norm("".join(parser.title_parts))
    summary = _norm("".join(parser.summary_parts))
    date_match = _DATE_RE.search(_norm("".join(parser.date_parts)))

    if not title:
        return None
    if date_match is None:
        return None
    if len(summary) < 40:
        return None
    if not parser.has_login_link:
        return None

    return {
        "title": title,
        "subtitle": parser.subtitle,
        "date": date_match.group(0),
        "summary": summary,
        "canonical_url": canonical,
    }


def is_tqfarma_login_page(html: str) -> bool:
    """True si `html` es la página de login del portal de tqfarma — a la que
    redirigen las ~1700 URLs gated del sitemap. Permite que el llamador las
    descarte sin una segunda llamada a webclaw."""
    return _LOGIN_OG_URL_RE.search(html) is not None


def build_news_text(parsed: dict) -> str:
    """Arma el texto que se ingesta al RAG para una noticia summary-only.

    Lleva el marcador SUMMARY_MARKER al inicio para que el prompt del sistema
    pueda detectar, en tiempo de respuesta, que esta fuente es solo un resumen.
    """
    lines = [
        SUMMARY_MARKER,
        "Este es únicamente el resumen público de una noticia de tqfarma. "
        "El artículo completo requiere iniciar sesión en el portal de "
        "profesionales de la salud.",
        "",
        f"Título: {parsed['title']}",
    ]
    if parsed.get("subtitle"):
        lines.append(f"Especialidad: {parsed['subtitle']}")
    lines.append(f"Fecha: {parsed['date']}")
    lines.append(f"Resumen: {parsed['summary']}")
    return "\n".join(lines)
