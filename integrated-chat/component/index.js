import { ChatWidget } from './chat-widget.js';

const stylesUrl = new URL('./styles.css', import.meta.url);
ChatWidget.cssText = await fetch(stylesUrl).then((r) => r.text());

if (!customElements.get('company-chat')) {
  customElements.define('company-chat', ChatWidget);
}

export { ChatWidget };
