# CLAUDE.md — `integrated-chat`

Contexto persistente para Claude Code en este sub-proyecto. La fuente de verdad funcional es [`SPEC.md`](./SPEC.md); este archivo es solo el mapa.

## Qué es esto

Sub-proyecto **independiente** del chatbot Python en `../tq_chatbot/`. Una alternativa client-side: el mismo Q&A pero corriendo entero en el navegador con la API nativa de IA de Chrome (Prompt API + Gemini Nano on-device), empaquetado como Web Component reutilizable.

**Importante: este sub-proyecto no toca el código Python del repo.** Vive completamente dentro de `integrated-chat/`.

## Stack

- HTML, CSS y JavaScript vanilla (módulos ES nativos).
- Web Components con Shadow DOM.
- Chrome Built-in AI exclusivamente (`LanguageModel` / Prompt API). Sin API keys, sin red para inferencia, sin frameworks, sin bundlers.
- Idioma del chatbot: español. Las sesiones se crean con `expectedInputs`/`expectedOutputs` en `["es"]`.

## Mapa de carpetas

```
integrated-chat/
├── component/         Web Component productizable. Self-contained.
│   ├── index.js       Define <company-chat>.
│   ├── chat-widget.js Custom element + Shadow DOM + UI + estado.
│   ├── styles.css     Estilos del Shadow DOM.
│   └── core/
│       ├── ai.js              Wrapper Prompt API.
│       ├── dom-reader.js      Extracción de texto limpio del DOM.
│       ├── sitemap.js         Sitemap fetch + ranking.
│       └── qa-orchestrator.js Flujo pregunta → DOM → fallback sitemap → respuesta.
├── extension/         Solo para la demo. Inyecta el componente sobre la web real de TQ.
│   ├── manifest.json  Manifest V3.
│   ├── content.js     ISOLATED world: importa el componente, lo inserta en el DOM.
│   └── background.js  Service worker: fetch de sitemap y páginas (CORS bypass).
└── demo/
    └── index.html     Página standalone para probar el componente sin extensión.
```

**Frontera de modularidad:** `component/` no debe importar nada de `extension/`. La extensión solo importa `component/index.js` y lo inserta. El día que TQ adopte el componente copia `component/` y agrega el tag — fin.

## Comandos

Servir el demo standalone (los módulos ES requieren HTTP, no `file://`):

```bash
cd integrated-chat
python3 -m http.server 8000
# abrir http://localhost:8000/demo/
```

Importante: el server **debe** correr desde `integrated-chat/`, no desde `demo/`. La página importa el componente con `../component/index.js` y `python3 -m http.server` no permite salir del docroot.

Cargar la extensión sin empaquetar (para la demo final):

1. Abrir `chrome://extensions/` y activar **Developer mode**.
2. Click en **Load unpacked** y seleccionar la carpeta `integrated-chat/extension/`.
3. Visitar `https://www.tqconfiable.com/` o `https://www.tqfarma.com/`.

Ver disponibilidad del modelo:

```js
await LanguageModel.availability()
// → 'available' | 'downloadable' | 'downloading' | 'unavailable'
```

## Convenciones del sub-proyecto

- Idioma del chatbot: español. Mantener literales de UI y prompts en español.
- Conservar los placeholders `{knowledge_base}` / `{question}` en cualquier prompt que se traiga del Python — no aplica acá pero referencia conceptual.
- `component/` no conoce a `extension/`. Si algo necesita acceso a APIs de extensión (`chrome.runtime`, `chrome.storage`), va en `extension/`.
- Los fetches a recursos de la web anfitriona (sitemap, páginas) se hacen desde `background.js` (service worker) en el contexto de la extensión, para evitar CORS y CSP del sitio.
- En el contexto del demo standalone, los fetches se hacen directamente desde el navegador (mismo origen) — por eso `core/sitemap.js` debe ser agnóstico al transporte.

## Documentación de referencia

- Prompt API: https://developer.chrome.com/docs/ai/prompt-api
- Built-in AI APIs (overview): https://developer.chrome.com/docs/ai/built-in-apis
- Structured output: https://developer.chrome.com/docs/ai/structured-output-for-prompt-api
- Session management: https://developer.chrome.com/docs/ai/session-management
