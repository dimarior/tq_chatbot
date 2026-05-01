// Carga y rankea URLs de un sitemap.xml. Usado como fallback cuando la página
// actual no contiene la respuesta a la pregunta del usuario.
//
// El módulo es agnóstico al transporte: por defecto usa fetch() del navegador,
// pero acepta un fetcher inyectable. La extensión Chrome (Capa 7) inyectará un
// fetcher que enruta a través del service worker (background.js) para evitar
// CORS y CSP del sitio anfitrión.

import { tokenize } from './dom-reader.js';

const DEFAULT_TIMEOUT_MS = 8000;

function defaultFetch(url, { signal } = {}) {
  // Mixed-content guard: muchos sitemaps (incluido el de tqconfiable.com)
  // listan URLs con http:// aunque el sitio se sirva por HTTPS. Cuando la
  // página anfitriona corre en HTTPS, los browsers bloquean fetches a http://
  // (mixed content). Subimos el scheme transparentemente.
  if (
    typeof location !== 'undefined' &&
    location.protocol === 'https:' &&
    url.startsWith('http://')
  ) {
    url = 'https://' + url.slice('http://'.length);
  }
  return fetch(url, { credentials: 'omit', signal }).then((r) => {
    if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
    return r.text();
  });
}

function withTimeout(fetcher, ms) {
  return (url) => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ms);
    return Promise.resolve(fetcher(url, { signal: ctrl.signal })).finally(() =>
      clearTimeout(timer),
    );
  };
}

// ---- Sitemap loading & parsing --------------------------------------------

// Carga un sitemap.xml y devuelve la lista plana de URLs.
// Resuelve sitemap indexes (un sitemap que apunta a otros sitemaps), bajando
// como máximo `maxIndexDepth` niveles para no quedarse atrapado.
export async function fetchSitemap(url, options = {}) {
  const {
    fetcher = defaultFetch,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    maxIndexDepth = 1,
    maxUrls = 500,
  } = options;
  const fetchWithTimeout = withTimeout(fetcher, timeoutMs);

  const queue = [{ url, depth: 0 }];
  const seen = new Set();
  const out = [];

  while (queue.length > 0 && out.length < maxUrls) {
    const { url: current, depth } = queue.shift();
    if (seen.has(current)) continue;
    seen.add(current);

    let xml;
    try {
      xml = await fetchWithTimeout(current);
    } catch (err) {
      console.warn('[sitemap] fetch failed', current, err);
      continue;
    }

    const parsed = parseSitemap(xml);
    if (parsed.type === 'index') {
      if (depth >= maxIndexDepth) continue;
      for (const child of parsed.urls) queue.push({ url: child, depth: depth + 1 });
    } else {
      for (const u of parsed.urls) {
        if (out.length >= maxUrls) break;
        out.push(u);
      }
    }
  }

  return out;
}

// Parser tolerante: detecta sitemapindex vs urlset y devuelve las URLs.
export function parseSitemap(xml) {
  const doc = new DOMParser().parseFromString(xml, 'application/xml');
  if (doc.querySelector('parsererror')) {
    return { type: 'urlset', urls: [] };
  }
  const indexLocs = doc.querySelectorAll('sitemap > loc');
  if (indexLocs.length > 0) {
    return {
      type: 'index',
      urls: [...indexLocs].map((n) => n.textContent.trim()).filter(Boolean),
    };
  }
  const urlLocs = doc.querySelectorAll('url > loc');
  return {
    type: 'urlset',
    urls: [...urlLocs].map((n) => n.textContent.trim()).filter(Boolean),
  };
}

// ---- Ranking de URLs por similitud léxica ---------------------------------

// Jaccard de tokens entre la query y los tokens del path/slug de cada URL.
// Devuelve hasta `topN` URLs con al menos un hit, ordenadas por hits desc.
export function rankUrls(urls, query, topN = 3) {
  const qTokens = new Set(tokenize(query));
  if (qTokens.size === 0) return urls.slice(0, topN);

  const scored = urls.map((u, index) => {
    const tokens = new Set(tokenizeUrl(u));
    let inter = 0;
    for (const t of qTokens) if (tokens.has(t)) inter++;
    const union = qTokens.size + tokens.size - inter;
    const jaccard = union > 0 ? inter / union : 0;
    return { url: u, hits: inter, jaccard, index };
  });

  scored.sort((a, b) => b.hits - a.hits || b.jaccard - a.jaccard || a.index - b.index);
  return scored.filter((s) => s.hits > 0).slice(0, topN).map((s) => s.url);
}

export function tokenizeUrl(url) {
  let path;
  try {
    const u = new URL(url);
    path = decodeURIComponent(u.pathname);
  } catch {
    path = url;
  }
  return tokenize(path.replace(/\.[a-z0-9]{1,5}$/i, '').replace(/[/\-_+]+/g, ' '));
}

// ---- Fetch de página HTML como cuerpo DOM ---------------------------------

// Carga una URL HTML y devuelve el <body> del documento parseado.
// El llamador puede usar las funciones de dom-reader sobre ese body.
export async function fetchPageBody(url, options = {}) {
  const { fetcher = defaultFetch, timeoutMs = DEFAULT_TIMEOUT_MS } = options;
  const fetchWithTimeout = withTimeout(fetcher, timeoutMs);
  const html = await fetchWithTimeout(url);
  const doc = new DOMParser().parseFromString(html, 'text/html');
  return doc.body || null;
}
