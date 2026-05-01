// Content script en ISOLATED world. Inyecta el componente como un módulo
// `<script type="module" src="chrome-extension://...">` para que se ejecute
// en MAIN world — necesario porque la Prompt API (`LanguageModel`) solo está
// disponible en MAIN, no en ISOLATED.
//
// Tradeoff: la inyección via `<script src>` está sujeta al CSP del sitio.
// Si una página objetivo tiene un `script-src` muy estricto que bloquea
// chrome-extension://, este enfoque falla y habría que migrar a
// content_scripts con `"world": "MAIN"` (chunk separado, sin acceso a
// chrome.runtime — requiere bridge por window.postMessage).
// Para los sitios de TQ esto debería funcionar; si no, ver KNOWN_ISSUES.md.

(() => {
  const ALREADY_INJECTED = '__tqAsistenteInjected';
  if (window[ALREADY_INJECTED]) return;
  window[ALREADY_INJECTED] = true;

  const componentUrl = chrome.runtime.getURL('component/index.js');

  const script = document.createElement('script');
  script.type = 'module';
  script.src = componentUrl;
  script.dataset.tqAsistente = '1';
  script.addEventListener('error', (e) => {
    console.error(
      '[tq-asistente] no se pudo cargar el componente (probable CSP del sitio).',
      e,
    );
  });
  script.addEventListener('load', () => {
    // El custom element ya quedó registrado en MAIN. Limpiar el tag para no
    // ensuciar el DOM del sitio.
    script.remove();
  });
  (document.head || document.documentElement).appendChild(script);

  // Insertar el widget. El upgrade del custom element ocurre asíncrono cuando
  // el módulo termine de cargar; mientras tanto el elemento queda inerte.
  const widget = document.createElement('company-chat');
  widget.setAttribute('sitemap-url', '/sitemap.xml');
  widget.setAttribute('position', 'bottom-right');
  // tqconfiable.com / tqfarma.com tienen su propio FAB redondo en bottom-right;
  // empujamos la burbuja hacia arriba para no encimarse.
  widget.style.setProperty('--cc-offset-bottom', '100px');

  const insert = () => (document.body || document.documentElement).appendChild(widget);
  if (document.body) insert();
  else document.addEventListener('DOMContentLoaded', insert, { once: true });
})();
