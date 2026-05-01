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
  }

  disconnectedCallback() {
    // Capa 3: aquí se llamará session.destroy() del wrapper de ai.js
  }

  attributeChangedCallback(name, _old, value) {
    if (!this._initialized) return;
    if (name === 'position') this._applyPosition(value);
    else if (name === 'accent-color') this._applyAccent(value);
    else if (name === 'placeholder') this._applyPlaceholder(value);
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

  async _onSubmit(e) {
    e.preventDefault();
    const text = this._input.value.trim();
    if (!text) return;
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

  // Capa 2: respuesta mock. Capa 3+ reemplaza esto por el orchestrator real.
  async _answer(question) {
    await new Promise((r) => setTimeout(r, 450));
    return {
      answer: `(mock) Recibí tu pregunta: "${question}". La integración con la IA on-device llega en la próxima capa.`,
      source: null,
    };
  }

  _setBusy(on) {
    this._input.disabled = on;
    this._sendBtn.disabled = on;
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
