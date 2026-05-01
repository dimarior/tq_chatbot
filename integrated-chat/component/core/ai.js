// Wrapper sobre la Prompt API de Chrome Built-in AI (LanguageModel + Gemini Nano on-device).
// Encapsula los 4 estados de availability(), el monitor de descarga del modelo,
// el evento contextoverflow y la creación/destrucción de sesión.
//
// Uso:
//   const ai = new AIClient({
//     system: 'Eres el asistente virtual de Tecnoquímicas...',
//     onStatusChange: (s) => console.log(s),
//     onDownloadProgress: (pct) => console.log(`${pct}%`),
//   });
//   await ai.init();                    // dispara availability check + descarga si aplica
//   const text = await ai.ask('Hola');  // string
//   ai.destroy();                       // limpiar al desmontar el componente

export const Status = Object.freeze({
  UNKNOWN: 'unknown',
  UNAVAILABLE: 'unavailable',
  DOWNLOADABLE: 'downloadable',
  DOWNLOADING: 'downloading',
  AVAILABLE: 'available',
  ERROR: 'error',
});

export class AIClient {
  constructor({
    system = '',
    languages = ['es'],
    temperature,
    topK,
    onStatusChange,
    onDownloadProgress,
  } = {}) {
    this._system = system;
    this._languages = languages;
    this._temperature = temperature;
    this._topK = topK;
    this._onStatusChange = onStatusChange ?? (() => {});
    this._onDownloadProgress = onDownloadProgress ?? (() => {});
    this._session = null;
    this._status = Status.UNKNOWN;
    this._creating = null;
  }

  get status() {
    return this._status;
  }

  get isReady() {
    return this._status === Status.AVAILABLE && !!this._session;
  }

  static isSupported() {
    return typeof globalThis.LanguageModel !== 'undefined';
  }

  // Llama a availability() y mapea al estado interno. No crea sesión.
  async checkAvailability() {
    if (!AIClient.isSupported()) {
      this._setStatus(Status.UNAVAILABLE);
      return Status.UNAVAILABLE;
    }
    try {
      const a = await globalThis.LanguageModel.availability();
      this._setStatus(a);
      return a;
    } catch (err) {
      console.error('[ai.js] availability() failed', err);
      this._setStatus(Status.ERROR);
      return Status.ERROR;
    }
  }

  // Punto de entrada típico: chequea disponibilidad y crea sesión si es posible.
  // Si availability === 'downloadable' o 'downloading', dispara la descarga.
  async init() {
    const a = await this.checkAvailability();
    if (a === Status.UNAVAILABLE || a === Status.ERROR) return a;
    await this._createSession(a);
    return this._status;
  }

  // Crea la sesión (descarga el modelo si hace falta).
  async _createSession(currentAvailability) {
    if (this._session) return this._session;
    if (this._creating) return this._creating;

    const options = {
      expectedInputs: [{ type: 'text', languages: this._languages }],
      expectedOutputs: [{ type: 'text', languages: this._languages }],
    };
    if (this._system) {
      options.initialPrompts = [{ role: 'system', content: this._system }];
    }
    if (typeof this._temperature === 'number') options.temperature = this._temperature;
    if (typeof this._topK === 'number') options.topK = this._topK;

    if (currentAvailability !== Status.AVAILABLE) {
      this._setStatus(Status.DOWNLOADING);
      options.monitor = (m) => {
        m.addEventListener('downloadprogress', (e) => {
          const loaded = typeof e.loaded === 'number' ? e.loaded : 0;
          const pct = Math.max(0, Math.min(100, Math.round(loaded * 100)));
          this._onDownloadProgress(pct);
        });
      };
    }

    this._creating = (async () => {
      try {
        const session = await globalThis.LanguageModel.create(options);
        this._attachSessionListeners(session);
        this._session = session;
        this._setStatus(Status.AVAILABLE);
        return session;
      } catch (err) {
        console.error('[ai.js] create() failed', err);
        this._setStatus(Status.ERROR);
        throw err;
      } finally {
        this._creating = null;
      }
    })();

    return this._creating;
  }

  _attachSessionListeners(session) {
    if (typeof session.addEventListener !== 'function') return;
    session.addEventListener('contextoverflow', () => {
      console.warn('[ai.js] contextoverflow event — recreando sesión');
      this._recreateSession();
    });
  }

  async _recreateSession() {
    try {
      this._session?.destroy?.();
    } catch (err) {
      console.warn('[ai.js] error al destruir sesión', err);
    }
    this._session = null;
    await this._createSession(Status.AVAILABLE);
  }

  // Devuelve la sesión, creándola si hace falta. Lanza si no hay soporte.
  async getSession() {
    if (this._session) return this._session;
    const a = await this.checkAvailability();
    if (a === Status.UNAVAILABLE || a === Status.ERROR) {
      throw new Error(`LanguageModel no disponible (estado: ${a})`);
    }
    return this._createSession(a);
  }

  // Ejecuta un prompt en una sesión clonada (stateless). La sesión base solo
  // sirve para cargar el system prompt una vez; cada ask() obtiene un clone
  // fresco para que cada Q&A sea independiente — sin contaminación entre
  // llamadas (crítico para el orchestrator, que hace múltiples prompts por
  // pregunta del usuario al iterar el sitemap).
  // Retorna string si streaming===false (default), o un AsyncIterable si true.
  async ask(prompt, { responseConstraint, signal, streaming = false } = {}) {
    const session = await this.getSession();
    const opts = {};
    if (responseConstraint) opts.responseConstraint = responseConstraint;
    if (signal) opts.signal = signal;

    let ephemeral;
    try {
      ephemeral = await session.clone({ signal });
    } catch (err) {
      // Si clone() no está disponible en este build, caemos al modo no
      // stateless — peor experiencia pero no rompe la app.
      console.warn('[ai.js] session.clone() falló, usando sesión compartida', err);
      if (streaming) return session.promptStreaming(prompt, opts);
      return session.prompt(prompt, opts);
    }

    if (streaming) {
      // No podemos auto-destruir: el caller itera el AsyncIterable después de
      // que retornemos. Devolvemos el iterable y dejamos que el GC se encargue.
      return ephemeral.promptStreaming(prompt, opts);
    }

    try {
      return await ephemeral.prompt(prompt, opts);
    } finally {
      try {
        ephemeral.destroy();
      } catch {
        /* ignore */
      }
    }
  }

  // Información del contexto de la sesión actual (puede no existir en builds viejos).
  contextInfo() {
    if (!this._session) return null;
    const usage = this._session.inputUsage ?? this._session.contextUsage;
    const quota = this._session.inputQuota ?? this._session.contextWindow;
    if (typeof usage !== 'number' || typeof quota !== 'number') return null;
    return { usage, quota, remaining: Math.max(0, quota - usage) };
  }

  destroy() {
    try {
      this._session?.destroy?.();
    } catch (err) {
      console.warn('[ai.js] error al destruir sesión', err);
    }
    this._session = null;
    this._creating = null;
    this._setStatus(Status.UNKNOWN);
  }

  _setStatus(s) {
    if (this._status === s) return;
    this._status = s;
    try {
      this._onStatusChange(s);
    } catch (err) {
      console.error('[ai.js] onStatusChange callback threw', err);
    }
  }
}
