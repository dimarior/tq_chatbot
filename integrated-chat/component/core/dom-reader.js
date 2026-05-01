// Extrae texto limpio del DOM de la página actual y lo trocea por headings.
// Heurística mini-Readability inline: descarta nav/footer/script/etc, prioriza
// main/article cuando existen, normaliza espacios y emite separadores de bloque.
//
// Uso típico desde el orchestrator:
//   import { readPageForQuestion } from './dom-reader.js';
//   const chunks = readPageForQuestion('¿qué hace TQ?', { maxChars: 4000, topN: 3 });
//   // chunks = [{ heading, text }, ...]

const REJECT_TAG_SELECTORS = [
  'nav',
  'footer',
  'aside',
  'script',
  'style',
  'noscript',
  'template',
  'iframe',
  'svg',
  'canvas',
  'form',
  'button',
  'input',
  'textarea',
  'select',
  'label',
  'company-chat',
];

const REJECT_ATTR_SELECTORS = [
  '[role="navigation"]',
  '[role="banner"]',
  '[role="contentinfo"]',
  '[role="search"]',
  '[role="dialog"]',
  '[role="alertdialog"]',
  '[role="complementary"]',
  '[aria-hidden="true"]',
  '[hidden]',
];

const REJECT_CLASS_SELECTORS = [
  '.advertisement',
  '.ads',
  '.ad-banner',
  '.cookie',
  '.cookies',
  '.cookie-banner',
  '.sidebar',
  '.menu',
  '.skip-link',
  '.breadcrumb',
  '.breadcrumbs',
  '.pagination',
  '.share',
  '.social',
  '.newsletter',
];

const REJECT_SELECTOR = [
  ...REJECT_TAG_SELECTORS,
  ...REJECT_ATTR_SELECTORS,
  ...REJECT_CLASS_SELECTORS,
].join(',');

const PREFER_SELECTOR = 'main, article, [role="main"], [role="article"]';

const BLOCK_TAGS = new Set([
  'address', 'article', 'aside', 'blockquote', 'br', 'div',
  'dd', 'dl', 'dt', 'fieldset', 'figcaption', 'figure',
  'footer', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header',
  'hr', 'li', 'main', 'nav', 'ol', 'p', 'pre', 'section',
  'table', 'tr', 'ul',
]);

const HEADING_TAGS = new Set(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']);

const BLOCK_PARAGRAPH_TAGS = new Set([
  'p', 'li', 'dd', 'dt', 'blockquote', 'pre',
  'figcaption', 'td', 'th', 'caption',
]);

// ---- Utilidades ------------------------------------------------------------

function cloneAndPrune(root) {
  const cloned = root.cloneNode(true);
  const toRemove = cloned.querySelectorAll(REJECT_SELECTOR);
  for (const el of toRemove) el.remove();
  return cloned;
}

function pickSource(prunedRoot) {
  const preferred = prunedRoot.querySelector(PREFER_SELECTOR);
  return preferred || prunedRoot;
}

function normalizeText(s) {
  return (s || '')
    .replace(/ /g, ' ')
    .replace(/[ \t\f\v]+/g, ' ')
    .replace(/ *\n */g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

// ---- Extracción de texto plano --------------------------------------------

export function extractPageText(root = document.body) {
  if (!root) return '';
  const pruned = cloneAndPrune(root);
  const source = pickSource(pruned);
  const parts = [];
  walkBlocks(source, parts);
  return normalizeText(parts.join('\n'));
}

function walkBlocks(node, parts) {
  if (!node) return;
  if (node.nodeType === Node.TEXT_NODE) {
    const t = node.textContent;
    if (t && t.trim()) parts.push(t.replace(/\s+/g, ' ').trim());
    return;
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return;

  const tag = node.tagName.toLowerCase();
  const isBlock = BLOCK_TAGS.has(tag);
  if (isBlock) parts.push('\n');
  for (const child of node.childNodes) walkBlocks(child, parts);
  if (isBlock) parts.push('\n');
}

// ---- Chunking por headings ------------------------------------------------

// Devuelve [{ heading, text }, ...] respetando jerarquía de h1..h6.
// Si un chunk supera maxChars, se subdivide por párrafos.
export function chunkByHeadings(root = document.body, options = {}) {
  const { maxChars = 4000 } = options;
  if (!root) return [];

  const pruned = cloneAndPrune(root);
  const source = pickSource(pruned);

  const chunks = [];
  const state = { heading: null, parts: [] };

  function flush() {
    const text = normalizeText(state.parts.join('\n\n'));
    if (text) chunks.push({ heading: state.heading, text });
    state.parts = [];
  }

  function walk(node) {
    if (!node) return;
    if (node.nodeType !== Node.ELEMENT_NODE) return;

    const tag = node.tagName.toLowerCase();

    if (HEADING_TAGS.has(tag)) {
      flush();
      state.heading = (node.textContent || '').replace(/\s+/g, ' ').trim() || null;
      return;
    }

    if (BLOCK_PARAGRAPH_TAGS.has(tag)) {
      const t = (node.textContent || '').replace(/\s+/g, ' ').trim();
      if (t) state.parts.push(t);
      return;
    }

    for (const child of node.childNodes) {
      if (child.nodeType === Node.ELEMENT_NODE) walk(child);
    }
  }

  walk(source);
  flush();

  return splitOversized(chunks, maxChars);
}

function splitOversized(chunks, maxChars) {
  const result = [];
  for (const chunk of chunks) {
    if (chunk.text.length <= maxChars) {
      result.push(chunk);
      continue;
    }
    const paragraphs = chunk.text.split(/\n{2,}/);
    let buf = '';
    for (const p of paragraphs) {
      const candidate = buf ? `${buf}\n\n${p}` : p;
      if (candidate.length > maxChars && buf) {
        result.push({ heading: chunk.heading, text: buf });
        buf = p;
      } else {
        buf = candidate;
      }
    }
    if (buf) result.push({ heading: chunk.heading, text: buf });
  }
  return result;
}

// ---- Ranking léxico (Jaccard ponderado por heading) -----------------------

const STOPWORDS_ES = new Set([
  'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
  'de', 'del', 'al', 'a', 'en', 'con', 'por', 'para', 'sobre', 'desde', 'hasta',
  'y', 'o', 'u', 'e', 'que', 'qué', 'como', 'cómo', 'cuando', 'cuándo', 'donde', 'dónde',
  'es', 'son', 'fue', 'fueron', 'sea', 'ser', 'estar', 'esta', 'estan', 'esta',
  'se', 'su', 'sus', 'mi', 'mis', 'tu', 'tus',
  'lo', 'le', 'les', 'me', 'te', 'nos', 'os',
  'no', 'si', 'pero', 'sino', 'aunque',
  'esto', 'eso', 'aquello', 'este', 'esta', 'ese', 'esa', 'aquel', 'aquella',
  'mas', 'muy', 'tambien', 'tambn', 'solo', 'solamente',
  'hay', 'ha', 'han', 'he', 'has',
]);

export function tokenize(s) {
  return (s || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9ñü\s]/gi, ' ')
    .split(/\s+/)
    .filter((t) => t.length >= 3 && !STOPWORDS_ES.has(t));
}

// Asigna score por overlap de tokens; bonus por match en heading.
export function rankChunks(chunks, query, topN = 3) {
  const qTokens = new Set(tokenize(query));
  if (qTokens.size === 0) return chunks.slice(0, topN);

  const scored = chunks.map((c, i) => {
    const bodyTokens = new Set(tokenize(c.text));
    const headingTokens = new Set(tokenize(c.heading || ''));
    let score = 0;
    for (const t of qTokens) {
      if (headingTokens.has(t)) score += 3;
      if (bodyTokens.has(t)) score += 1;
    }
    return { chunk: c, score, index: i };
  });

  scored.sort((a, b) => b.score - a.score || a.index - b.index);
  const top = scored.slice(0, topN).filter((s) => s.score > 0);
  return top.map((s) => s.chunk);
}

// ---- Función de alto nivel para el orchestrator ---------------------------

// Devuelve los chunks relevantes para una pregunta, respetando un budget total.
// - Si todos los chunks juntos caben en budgetChars, los devuelve completos.
// - Si no, rankea y devuelve los top-N (o más, hasta llenar el budget).
export function readPageForQuestion(question, options = {}) {
  const {
    root = document.body,
    maxChunkChars = 4000,
    topN = 5,
    budgetChars = 12000,
  } = options;

  const chunks = chunkByHeadings(root, { maxChars: maxChunkChars });
  if (chunks.length === 0) return [];

  const totalChars = chunks.reduce((s, c) => s + c.text.length, 0);
  if (totalChars <= budgetChars) return chunks;

  const ranked = rankChunks(chunks, question, topN);
  if (ranked.length === 0) return chunks.slice(0, topN);

  // Llenar hasta budgetChars en orden de relevancia
  const out = [];
  let used = 0;
  for (const c of ranked) {
    if (used + c.text.length > budgetChars && out.length > 0) break;
    out.push(c);
    used += c.text.length;
  }
  return out;
}

// Serializa los chunks a un solo string apto para pasar al LLM como contexto.
export function chunksToContext(chunks) {
  return chunks
    .map((c) => (c.heading ? `## ${c.heading}\n${c.text}` : c.text))
    .join('\n\n')
    .trim();
}
