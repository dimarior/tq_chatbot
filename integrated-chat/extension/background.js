// Service worker de la extensión. Por ahora actúa como stub.
//
// El componente hace fetches mismo-origen desde el contexto de la página
// (sitemap.xml y otras páginas del sitio anfitrión), por lo que no requiere
// proxy a través de este service worker en el caso normal.
//
// Si en el futuro un sitio tiene un `connect-src` estricto que bloquee fetch
// directo de sitemap o páginas, aquí se implementaría un handler de
// chrome.runtime.onMessage que reciba `{type:'fetch', url}` y devuelva el
// texto. El orchestrator ya acepta un `fetcher` inyectable para enchufarlo.

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});
