import { AIClient, Status } from './core/ai.js';
import { QAOrchestrator } from './core/qa-orchestrator.js';

const TEMPLATE = `
  <button class="bubble" type="button" aria-label="Abrir chat" part="bubble">
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 4h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H8.5L4 21V5a1 1 0 0 1 1-1zm3 6h10v2H7v-2zm0-3h10v2H7V7z" fill="currentColor"/>
    </svg>
  </button>
  <div class="panel" role="dialog" aria-label="Asistente TQ" hidden>
    <header class="panel-header">
      <span class="panel-title">Asistente TQ</span>
      <button class="panel-close" type="button" aria-label="Cerrar">&times;</button>
    </header>
    <div class="disclaimer" hidden>
      <p>Tu pregunta nunca sale del navegador. La IA corre directamente en tu dispositivo.</p>
      <button type="button" class="disclaimer-ack">Entendido</button>
    </div>
    <div class="status-banner" hidden>
      <p class="status-msg"></p>
      <div class="status-progress" hidden><div class="status-progress-bar"></div></div>
      <button type="button" class="status-action" hidden></button>
      <details class="status-help" hidden>
        <summary>¿Cómo habilitarlo?</summary>
        <ol>
          <li>Usa Chrome 138 o superior.</li>
          <li>Abre <code>chrome://flags/#prompt-api-for-gemini-nano</code> y ponlo en <em>Enabled</em>.</li>
          <li>Reinicia Chrome y vuelve a abrir esta página.</li>
        </ol>
      </details>
    </div>
    <div class="messages" role="log" aria-live="polite" aria-relevant="additions">
      <p class="empty-state">Hazme una pregunta sobre Tecnoquímicas.<br/>Leeré la página actual para responder.</p>
    </div>
    <form class="composer" autocomplete="off">
      <input type="text" name="q" required aria-label="Tu pregunta" />
      <button type="submit" aria-label="Enviar">→</button>
    </form>
  </div>
`;

const POSITIONS = new Set(['bottom-right', 'bottom-left', 'top-right', 'top-left']);
const DEFAULT_PLACEHOLDER = 'Pregúntame sobre Tecnoquímicas...';

const SYSTEM_PROMPT = [
  'Eres el asistente virtual de Tecnoquímicas S.A., una compañía colombiana del sector farmacéutico y de consumo masivo fundada en 1934.',
  'Responde siempre en español, de forma clara y breve (máximo 4 oraciones cuando sea posible).',
  'Si no tienes información suficiente para responder con certeza, dilo explícitamente; nunca inventes datos.',
  'No respondas en otro idioma aunque te lo pidan.',
].join(' ');

export class ChatWidget extends HTMLElement {
  static cssText = '';

  static get observedAttributes() {
    return ['position', 'accent-color', 'placeholder', 'sitemap-url'];
  }

  constructor() {
    super();
    this._open = false;
    this._disclaimerSeen = false;
    this._messages = [];
    this._initialized = false;
    this._ai = null;
    this._orchestrator = null;
    this._aiInitStarted = false;
  }

  connectedCallback() {
    if (this._initialized) return;
    this._initialized = true;

    const shadow = this.attachShadow({ mode: 'open' });

    const style = document.createElement('style');
    style.textContent = ChatWidget.cssText;
    shadow.appendChild(style);

    const root = document.createElement('div');
    root.className = 'host';
    root.innerHTML = TEMPLATE;
    shadow.appendChild(root);

    this._root = root;
    this._bubble = root.querySelector('.bubble');
    this._panel = root.querySelector('.panel');
    this._panelClose = root.querySelector('.panel-close');
    this._disclaimer = root.querySelector('.disclaimer');
    this._disclaimerAck = root.querySelector('.disclaimer-ack');
    this._statusBanner = root.querySelector('.status-banner');
    this._statusMsg = root.querySelector('.status-msg');
    this._statusProgress = root.querySelector('.status-progress');
    this._statusProgressBar = root.querySelector('.status-progress-bar');
    this._statusAction = root.querySelector('.status-action');
    this._statusHelp = root.querySelector('.status-help');
    this._messagesEl = root.querySelector('.messages');
    this._emptyState = root.querySelector('.empty-state');
    this._form = root.querySelector('.composer');
    this._input = root.querySelector('input[name="q"]');
    this._sendBtn = this._form.querySelector('button[type="submit"]');

    this._applyPosition(this.getAttribute('position'));
    this._applyAccent(this.getAttribute('accent-color'));
    this._applyPlaceholder(this.getAttribute('placeholder'));

    this._bubble.addEventListener('click', () => this._toggle());
    this._panelClose.addEventListener('click', () => this._toggle(false));
    this._disclaimerAck.addEventListener('click', () => this._dismissDisclaimer());
    this._form.addEventListener('submit', (e) => this._onSubmit(e));
    this._statusAction.addEventListener('click', () => this._onStatusAction());

    this._ai = new AIClient({
      system: SYSTEM_PROMPT,
      languages: ['es'],
      onStatusChange: (s) => this._renderStatus(s),
      onDownloadProgress: (pct) => this._renderDownloadProgress(pct),
    });
    this._orchestrator = new QAOrchestrator({
      ai: this._ai,
      sitemapUrl: this.getAttribute('sitemap-url') || null,
    });

    // Render explícito del estado UNKNOWN antes del chequeo asíncrono, para
    // dejar el composer deshabilitado hasta confirmar disponibilidad.
    this._renderStatus(Status.UNKNOWN);
    this._ai.checkAvailability();
  }

  disconnectedCallback() {
    this._ai?.destroy();
    this._ai = null;
    this._orchestrator = null;
  }

  attributeChangedCallback(name, _old, value) {
    if (!this._initialized) return;
    if (name === 'position') this._applyPosition(value);
    else if (name === 'accent-color') this._applyAccent(value);
    else if (name === 'placeholder') this._applyPlaceholder(value);
    else if (name === 'sitemap-url') this._orchestrator?.setSitemapUrl(value || null);
  }

  _applyPosition(value) {
    const pos = POSITIONS.has(value) ? value : 'bottom-right';
    this._root.dataset.position = pos;
  }

  _applyAccent(value) {
    if (value) this._root.style.setProperty('--cc-accent', value);
    else this._root.style.removeProperty('--cc-accent');
  }

  _applyPlaceholder(value) {
    this._input.placeholder = value || DEFAULT_PLACEHOLDER;
  }

  _toggle(force) {
    this._open = typeof force === 'boolean' ? force : !this._open;
    this._panel.hidden = !this._open;
    this._root.classList.toggle('open', this._open);
    if (this._open) {
      if (!this._disclaimerSeen) this._disclaimer.hidden = false;
      requestAnimationFrame(() => this._input.focus());
    }
  }

  _dismissDisclaimer() {
    this._disclaimerSeen = true;
    this._disclaimer.hidden = true;
    this._input.focus();
  }

  // ---- Estado del modelo ----------------------------------------------------

  _renderStatus(status) {
    const banner = this._statusBanner;
    banner.dataset.state = status;

    this._statusProgress.hidden = status !== Status.DOWNLOADING;
    this._statusHelp.hidden = status !== Status.UNAVAILABLE;
    this._statusAction.hidden = true;
    this._statusAction.disabled = false;

    let visible = true;
    let inputEnabled = false;

    switch (status) {
      case Status.AVAILABLE:
        visible = false;
        inputEnabled = true;
        break;
      case Status.UNAVAILABLE:
        this._statusMsg.textContent =
          'Tu navegador no soporta IA on-device. Para usar este asistente necesitas Chrome con la Prompt API habilitada.';
        break;
      case Status.DOWNLOADABLE:
        this._statusMsg.textContent =
          'El modelo de IA on-device está disponible para descargar (~2 GB). La descarga ocurre una sola vez.';
        this._statusAction.hidden = false;
        this._statusAction.textContent = 'Descargar modelo';
        break;
      case Status.DOWNLOADING:
        this._statusMsg.textContent = 'Descargando el modelo de IA on-device...';
        break;
      case Status.ERROR:
        this._statusMsg.textContent =
          'Hubo un error inicializando el modelo. Revisa la consola e intenta de nuevo.';
        this._statusAction.hidden = false;
        this._statusAction.textContent = 'Reintentar';
        break;
      default:
        // UNKNOWN: aún no chequeamos
        this._statusMsg.textContent = 'Verificando disponibilidad del modelo...';
    }

    banner.hidden = !visible;
    this._setComposerEnabled(inputEnabled);
  }

  _renderDownloadProgress(pct) {
    this._statusProgressBar.style.width = `${pct}%`;
    this._statusMsg.textContent = `Descargando el modelo de IA on-device... ${pct}%`;
  }

  async _onStatusAction() {
    if (!this._ai) return;
    const status = this._ai.status;
    if (status === Status.DOWNLOADABLE || status === Status.ERROR) {
      this._statusAction.disabled = true;
      try {
        await this._ai.init();
      } catch (err) {
        console.error('[company-chat] init falló', err);
      }
    }
  }

  _setComposerEnabled(enabled) {
    this._input.disabled = !enabled;
    this._sendBtn.disabled = !enabled;
  }

  // ---- Conversación ---------------------------------------------------------

  async _onSubmit(e) {
    e.preventDefault();
    const text = this._input.value.trim();
    if (!text) return;
    if (!this._ai || this._ai.status !== Status.AVAILABLE) return;

    this._input.value = '';
    this._setBusy(true);
    this._addMessage({ role: 'user', text });
    this._setTyping(true);
    try {
      const reply = await this._answer(text);
      this._addMessage({ role: 'assistant', text: reply.answer, source: reply.source });
    } catch (err) {
      this._addMessage({
        role: 'assistant',
        text: 'Tuve un problema procesando tu pregunta. Inténtalo de nuevo.',
      });
      console.error('[company-chat]', err);
    } finally {
      this._setTyping(false);
      this._setBusy(false);
      this._input.focus();
    }
  }

  // Capa 6: orchestrator + fallback al sitemap. La fuente puede ser:
  //   - 'current' (página actual) → no se renderiza link
  //   - una URL → link clicable a la fuente
  //   - null → no se encontró respuesta
  // Cuando found=false ignoramos el texto del modelo (que tiende a meter datos
  // tangenciales) y mostramos un mensaje limpio fijo. El texto crudo queda en el
  // log de debug.
  async _answer(question) {
    const result = await this._orchestrator.ask(question);
    let answer;
    if (result.found && result.answer) {
      answer = result.answer;
    } else if (result.found) {
      answer = 'No tengo más detalles sobre eso.';
    } else {
      answer = 'No encontré información sobre eso en este sitio.';
    }
    const source = result.source && result.source !== 'current' ? result.source : null;
    return { answer, source };
  }

  _setBusy(on) {
    this._input.disabled = on || this._ai?.status !== Status.AVAILABLE;
    this._sendBtn.disabled = on || this._ai?.status !== Status.AVAILABLE;
  }

  _addMessage(msg) {
    this._messages.push(msg);
    if (this._emptyState && this._emptyState.parentElement === this._messagesEl) {
      this._emptyState.remove();
    }
    const el = document.createElement('div');
    el.className = `msg msg-${msg.role}`;
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.textContent = msg.text;
    el.appendChild(bubble);
    if (msg.source) {
      const cite = document.createElement('a');
      cite.className = 'msg-source';
      cite.href = msg.source;
      cite.target = '_blank';
      cite.rel = 'noopener noreferrer';
      cite.textContent = `Fuente: ${msg.source}`;
      el.appendChild(cite);
    }
    this._messagesEl.appendChild(el);
    this._messagesEl.scrollTop = this._messagesEl.scrollHeight;
  }

  _setTyping(on) {
    let typingEl = this._messagesEl.querySelector('.msg-typing');
    if (on && !typingEl) {
      typingEl = document.createElement('div');
      typingEl.className = 'msg msg-assistant msg-typing';
      typingEl.innerHTML = '<div class="msg-bubble"><span></span><span></span><span></span></div>';
      this._messagesEl.appendChild(typingEl);
      this._messagesEl.scrollTop = this._messagesEl.scrollHeight;
    } else if (!on && typingEl) {
      typingEl.remove();
    }
  }
}
