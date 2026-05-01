// Orquesta el flujo Q&A: pregunta → contexto del DOM → prompt al modelo →
// respuesta estructurada → fallback al sitemap si la página actual no basta.

import { readPageForQuestion, chunksToContext } from './dom-reader.js';
import { fetchSitemap, fetchPageBody, rankUrls } from './sitemap.js';

// JSON Schema para responseConstraint del Prompt API.
//   - found: si la información para responder está en el contexto
//   - answer: la respuesta en español, breve (máx 4 oraciones)
//   - confidence: 0..1 — qué tan seguro está de que la respuesta es correcta
export const ANSWER_SCHEMA = Object.freeze({
  type: 'object',
  required: ['found', 'answer', 'confidence'],
  additionalProperties: false,
  properties: {
    found: {
      type: 'boolean',
      description:
        'true si el contexto tiene información suficiente para responder la pregunta; false en caso contrario.',
    },
    answer: {
      type: 'string',
      description:
        'Respuesta en español al usuario. Si found=false, una explicación breve de que no se encontró la información.',
    },
    confidence: {
      type: 'number',
      minimum: 0,
      maximum: 1,
      description: 'Confianza en la respuesta, entre 0 y 1.',
    },
  },
});

const DEFAULT_DOM_OPTIONS = {
  topN: 6,
  budgetChars: 12000,
  maxChunkChars: 4000,
};

const DEFAULT_CONFIDENCE_THRESHOLD = 0.5;
const DEFAULT_FALLBACK_TOP_PAGES = 2;

export class QAOrchestrator {
  constructor({
    ai,
    confidenceThreshold = DEFAULT_CONFIDENCE_THRESHOLD,
    sitemapUrl = null,
    fetcher = null,
    fallbackTopPages = DEFAULT_FALLBACK_TOP_PAGES,
  } = {}) {
    if (!ai) throw new Error('QAOrchestrator requires an ai client');
    this._ai = ai;
    this._confidenceThreshold = confidenceThreshold;
    this._sitemapUrl = sitemapUrl;
    this._fetcher = fetcher;
    this._fallbackTopPages = fallbackTopPages;
    this._sitemapCache = null;
  }

  setSitemapUrl(url) {
    if (this._sitemapUrl !== url) {
      this._sitemapUrl = url;
      this._sitemapCache = null;
    }
  }

  // Devuelve { answer, source, found, confidence, chunksUsed }
  // - source: 'current' si vino de la página actual, una URL si vino del sitemap, null si no
  async ask(question, options = {}) {
    const t0 = performance.now();
    const primary = await this._askWithRoot(question, document.body, options);

    if (!this.shouldFallback(primary) || !this._sitemapUrl) {
      logDebug({
        question,
        elapsedMs: performance.now() - t0,
        primary,
        fallback: null,
        chosen: primary,
      });
      return primary;
    }

    // Fallback: sitemap → ranking → fetch top-N → reintento
    const fallback = await this._tryFallback(question, options);
    const chosen = fallback && this._isBetter(fallback, primary) ? fallback : primary;

    logDebug({
      question,
      elapsedMs: performance.now() - t0,
      primary,
      fallback,
      chosen,
    });
    return chosen;
  }

  async _askWithRoot(question, root, options = {}) {
    const domOpts = { ...DEFAULT_DOM_OPTIONS, ...(options.dom ?? {}) };
    const chunks = readPageForQuestion(question, { ...domOpts, root });
    const context = chunksToContext(chunks);

    if (!context) {
      return {
        answer: 'No pude leer el contenido de esta página.',
        source: null,
        found: false,
        confidence: 0,
        chunksUsed: 0,
      };
    }

    const prompt = buildPrompt(question, context);
    const raw = await this._ai.ask(prompt, { responseConstraint: ANSWER_SCHEMA });
    const parsed = parseResponse(raw);

    return {
      answer: (parsed.answer || '').trim(),
      source: parsed.found ? 'current' : null,
      found: !!parsed.found,
      confidence: typeof parsed.confidence === 'number' ? parsed.confidence : 0,
      chunksUsed: chunks.length,
      raw,
    };
  }

  async _tryFallback(question, options = {}) {
    let urls;
    try {
      urls = await this._loadSitemap();
    } catch (err) {
      console.warn('[qa-orchestrator] sitemap load failed', err);
      return null;
    }
    if (!urls || urls.length === 0) return null;

    // Excluir la página actual de los candidatos. Normalizamos para que
    // /demo/ y /demo/index.html cuenten como la misma URL.
    const currentNorm = normalizeUrl(location.href);
    const candidates = urls.filter((u) => normalizeUrl(u) !== currentNorm);
    if (candidates.length === 0) return null;

    let ranked = rankUrls(candidates, question, this._fallbackTopPages);
    let strategy = 'lexical';
    if (ranked.length === 0) {
      // Sin hits léxicos en los slugs: intentar las primeras N URLs igual.
      // Cubre casos de slugs no descriptivos (p.ej. /pages/123) o sitemaps pequeños.
      ranked = candidates.slice(0, this._fallbackTopPages);
      strategy = 'blind';
    }
    console.info(
      `[qa-orchestrator] fallback (${strategy}) → ${ranked.length} URL(s)`,
      ranked,
    );

    let best = null;
    for (const url of ranked) {
      let body;
      try {
        body = await fetchPageBody(url, { fetcher: this._fetcher ?? undefined });
      } catch (err) {
        console.warn('[qa-orchestrator] fetchPageBody failed', url, err);
        continue;
      }
      if (!body) continue;

      let result;
      try {
        result = await this._askWithRoot(question, body, options);
      } catch (err) {
        console.warn('[qa-orchestrator] askWithRoot failed for', url, err);
        continue;
      }
      result.source = result.found ? url : null;
      result.url = url;
      if (this._isBetter(result, best)) best = result;
      if (result.found && result.confidence >= this._confidenceThreshold) break;
    }
    return best;
  }

  async _loadSitemap() {
    if (this._sitemapCache) return this._sitemapCache;
    if (!this._sitemapUrl) return [];
    const urls = await fetchSitemap(this._sitemapUrl, {
      fetcher: this._fetcher ?? undefined,
    });
    this._sitemapCache = urls;
    return urls;
  }

  _isBetter(candidate, current) {
    if (!current) return !!candidate;
    if (!candidate) return false;
    // found=true gana
    if (candidate.found && !current.found) return true;
    if (!candidate.found && current.found) return false;
    // a igualdad de found, confidence manda
    return candidate.confidence > current.confidence;
  }

  shouldFallback(result) {
    if (!result) return true;
    if (!result.found) return true;
    if (result.confidence < this._confidenceThreshold) return true;
    return false;
  }
}

function buildPrompt(question, context) {
  return [
    'Tienes a continuación información extraída de una página web.',
    'Tu tarea es responder la pregunta ESPECÍFICA del usuario usando ÚNICAMENTE esa información.',
    '',
    'Reglas estrictas:',
    '- found=true SOLO si el contexto responde específicamente lo que el usuario pregunta. Si el contexto menciona el tema pero no responde la pregunta concreta (por ejemplo: pregunta "¿quién fundó X?" y el contexto solo dice "X fue fundada en 1934" sin mencionar al fundador), devuelve found=false.',
    '- Si found=false, en answer escribe ÚNICAMENTE una oración corta diciendo que no encontraste esa información específica. NO menciones datos tangencialmente relacionados ni respuestas parciales (ejemplo prohibido: "no encontré la fundación de TQ Farma, pero Tecnoquímicas se fundó en 1934"). Solo: "No encontré información sobre <tema>".',
    '- Nunca inventes datos, nombres, fechas o cifras que no estén explícitos en el contexto.',
    '- Responde siempre en español, de forma clara y breve (máximo 4 oraciones).',
    '- confidence debe reflejar qué tan completa y específica es tu respuesta respecto a lo que pregunta el usuario; si solo tienes información parcial o tangencial, baja confidence.',
    '',
    '=== Información de la página ===',
    context,
    '=== Fin de la información ===',
    '',
    `Pregunta del usuario: ${question}`,
  ].join('\n');
}

function logDebug({ question, elapsedMs, primary, fallback, chosen }) {
  const ok = chosen?.found && chosen.confidence >= 0.5;
  const tagColor = ok ? '#0a6e3b' : '#b76e00';
  const label = ok ? 'found' : 'not-found';
  const sourceLabel =
    chosen?.source === 'current' ? 'página actual' : chosen?.source ? 'sitemap' : 'sin fuente';
  console.groupCollapsed(
    `%c[qa-orchestrator]%c ${label} %c"${question}" %c(${elapsedMs.toFixed(0)} ms · conf ${(chosen?.confidence ?? 0).toFixed(2)} · ${sourceLabel})`,
    `color:#fff;background:${tagColor};padding:2px 6px;border-radius:3px;font-weight:600`,
    'color:inherit',
    'color:#1a1a1a;font-weight:500',
    'color:#6b7280;font-weight:normal',
  );
  console.log('chosen  ', chosen);
  console.log('primary ', primary);
  if (fallback !== null) console.log('fallback', fallback);
  console.groupEnd();
}

// Normaliza URLs para comparar identidad de página: descarta hash y query,
// trata `/foo/` como equivalente a `/foo/index.html`, y upgrade http→https
// cuando la página actual es HTTPS (sitemaps suelen listar http aunque el
// sitio sirva por https).
function normalizeUrl(u) {
  try {
    const url = new URL(u);
    url.hash = '';
    url.search = '';
    if (url.pathname.endsWith('/')) url.pathname += 'index.html';
    if (
      typeof location !== 'undefined' &&
      location.protocol === 'https:' &&
      url.protocol === 'http:'
    ) {
      url.protocol = 'https:';
    }
    return url.toString();
  } catch {
    return u;
  }
}

function parseResponse(raw) {
  if (raw && typeof raw === 'object') return raw;
  if (typeof raw !== 'string') {
    return { found: false, answer: '', confidence: 0 };
  }
  const trimmed = raw.trim();
  try {
    return JSON.parse(trimmed);
  } catch {
    const match = trimmed.match(/\{[\s\S]*\}/);
    if (match) {
      try {
        return JSON.parse(match[0]);
      } catch {
        /* fallthrough */
      }
    }
    return { found: true, answer: trimmed, confidence: 0.5 };
  }
}
