# SPEC — `integrated-chat`

Fuente de verdad funcional del sub-proyecto. Si el código y este documento divergen, gana este documento (o se actualiza explícitamente).

## Objetivo

Una alternativa **client-side** al chatbot Q&A de Tecnoquímicas: el mismo producto, pero corriendo entero en el navegador del usuario con el **API nativa de IA de Chrome** (Prompt API + Gemini Nano on-device). Empaquetado como Web Component (`<company-chat></company-chat>`).

Para la presentación final el componente se demuestra inyectado vía una **extensión de Chrome** sobre la web real de TQ. En producción la empresa lo adopta copiando `component/` + un solo tag.

**Narrativa de innovación:** cero costo de inferencia · cero latencia de red · datos del usuario nunca salen del navegador · integración con un solo tag.

## Contexto del proyecto

Este es un sub-proyecto **independiente** del chatbot Python (`tq_chatbot/`). No comparte código ni configuración. El equipo principal mantiene el flujo Gemini-en-la-nube; este sub-proyecto explora la alternativa on-device.

## Decisiones cerradas

| Tema | Decisión |
|---|---|
| Dominios de la demo | Ambos: `www.tqconfiable.com` y `www.tqfarma.com`. |
| Idioma del chatbot | Español. `expectedInputs`/`expectedOutputs` con `["es"]` al crear sesión. |
| Fallback si `LanguageModel` no disponible | Mensaje + instrucciones de habilitación (versión Chrome, flag `chrome://flags/#prompt-api-for-gemini-nano`). **No** se llama al backend Python — preserva la narrativa on-device. |
| Look default | Azul corporativo TQ (`#0033A0`), burbuja `bottom-right`, placeholder `"Pregúntame sobre Tecnoquímicas..."`. Configurable vía atributos. |
| Sitemap | Confirmado en ambos dominios. URL default `/sitemap.xml`. Atributo `sitemap-url` permite override. |
| Disclaimer de privacidad | Sí — banner pequeño la primera vez que se abre el panel en cada sesión. |
| Cita de fuente | Sí — cuando la respuesta venga del sitemap (no del DOM actual), incluir link clicable a la URL fuente. |
| CSP estricto del sitio | Asumido. Carga del componente desde el ISOLATED world del content script vía `import(chrome.runtime.getURL(...))`. Fetches de sitemap/páginas se enrutan por `background.js`. |

## Stack técnico

- HTML, CSS y JavaScript vanilla (módulos ES nativos).
- Web Components con Shadow DOM (aislamiento de estilos respecto a la web anfitriona).
- Chrome Built-in AI exclusivamente (Prompt API). Sin API keys, sin red para inferencia.
- Sin React, sin Vue, sin bundlers complejos. Si hace falta, import maps.

## Estructura

```
integrated-chat/
├── README.md
├── SPEC.md                          (este archivo)
├── CLAUDE.md
├── component/                       Web Component productizable
│   ├── index.js                     Entry: customElements.define('company-chat', ...)
│   ├── chat-widget.js               Custom element + Shadow DOM + estado + UI
│   ├── styles.css                   Estilos del Shadow DOM
│   └── core/
│       ├── ai.js                    Wrapper Prompt API
│       ├── dom-reader.js            Extracción de texto limpio del DOM actual
│       ├── sitemap.js               Parseo + ranking de URLs por relevancia
│       └── qa-orchestrator.js       Flujo: pregunta → DOM → fallback sitemap → respuesta
├── extension/                       Solo para la demo
│   ├── manifest.json                Manifest V3
│   ├── content.js                   ISOLATED world: importa el componente y lo inyecta
│   ├── background.js                Service worker: fetch de sitemap/páginas (CORS bypass)
│   └── icons/
└── demo/
    └── index.html                   Página standalone (sin extensión)
```

**Principio de modularidad:** `component/` no sabe que existe `extension/`. La extensión solo importa el componente y lo inserta en el DOM. La empresa adopta el componente copiando `component/` y agregando el tag.

## API del componente

```html
<company-chat
  sitemap-url="/sitemap.xml"
  position="bottom-right"
  accent-color="#0033A0"
  placeholder="Pregúntame sobre Tecnoquímicas..."
></company-chat>
```

| Atributo | Default | Descripción |
|---|---|---|
| `sitemap-url` | `/sitemap.xml` | URL del sitemap consultado como fallback. |
| `position` | `bottom-right` | `bottom-right` · `bottom-left` · `top-right` · `top-left`. |
| `accent-color` | `#0033A0` | Color principal de la burbuja, header y mensajes del usuario. |
| `placeholder` | `Pregúntame sobre Tecnoquímicas...` | Texto del input. |

Estado: historial de la conversación en memoria (no persiste entre recargas).

## Flujo de Q&A

1. Usuario escribe pregunta.
2. `dom-reader` extrae texto limpio del DOM actual (descarta `nav/footer/script/style/aside`, prioriza `article/main/section`).
3. Si excede el contexto del modelo (`session.inputQuota`), trocear por headings y rankear chunks por similitud léxica con la pregunta.
4. Prompt al modelo con `responseConstraint` JSON Schema: `{ found: boolean, answer: string, confidence: number }` y system prompt anti-alucinación.
5. Si `found === false` o `confidence` está bajo umbral:
   1. Pedir sitemap (vía background si estamos en la extensión).
   2. Rankear URLs por Jaccard de tokens (slug + path) vs tokens de la pregunta.
   3. Fetch top 2-3, extraer texto, reintentar prompt por cada una hasta `found === true`.
6. Devolver `{ answer, source: 'current' | <url> }` y renderizar. Si `source` es URL, mostrar link.

## Manejo de `LanguageModel.availability()`

| Estado | UX |
|---|---|
| `available` | Modo normal. |
| `downloadable` / `downloading` | Banner con barra de progreso vía `monitor` listener. Input deshabilitado hasta `available`. |
| `unavailable` | Banner con instrucciones: requiere Chrome ≥ 138, flag `chrome://flags/#prompt-api-for-gemini-nano`. Input deshabilitado. **No** se hace fallback al backend Python. |

`session.addEventListener('contextoverflow', ...)` recrea la sesión.
`disconnectedCallback` del componente llama `session.destroy()`.

## Plan de implementación (checklist)

- [x] **Capa 1 — Bootstrap:** crear `integrated-chat/` con `README.md`, `SPEC.md`, `CLAUDE.md`.
- [x] **Capa 2 — Esqueleto Web Component + UI con mocks:** `component/index.js`, `chat-widget.js`, `styles.css`, `demo/index.html`. Burbuja flotante azul, panel, mensajes, respuestas mock.
- [ ] **Capa 3 — `core/ai.js`:** wrapper completo del Prompt API con los 4 estados de `availability()`. Reemplaza los mocks.
- [ ] **Capa 4 — `core/dom-reader.js`:** extracción limpia y chunking del DOM actual.
- [ ] **Capa 5 — `core/qa-orchestrator.js` (parcial):** flujo pregunta → DOM → respuesta. Aún sin sitemap.
- [ ] **Capa 6 — `core/sitemap.js` + integración del fallback:** ranking Jaccard, cita de fuente.
- [ ] **Capa 7 — Extensión MV3:** `manifest.json`, `content.js`, `background.js`. Carga unpacked, inyecta en ambos dominios.
- [ ] **Capa 8 — Pulido final:** disclaimer en producción, README final con instrucciones de demo.

Después de cada capa el implementador pausa y pide verificación al usuario antes de continuar.

## Criterios de éxito de la presentación

- La burbuja se abre en la página real de TQ (vía la extensión cargada como unpacked).
- Responde en español a preguntas sobre el contenido visible en la página actual.
- Si la respuesta no está en la página actual, navega el sitemap, encuentra la página relevante, y cita la URL fuente.
- Funciona sin red después de la descarga inicial del modelo.
- Adoptarlo en producción = copiar `component/` y agregar el tag a la HTML.

## Anti-objetivos

- No agregar frameworks ni dependencias npm pesadas.
- No mezclar código de la extensión dentro del componente.
- No usar `localStorage`/`sessionStorage` salvo que sea imprescindible.
- No emitir estilos fuera del Shadow DOM (puede romper la web anfitriona).
- No tocar el código Python existente (`tq_chatbot/`) por ningún motivo.
- No llamar a APIs externas ni a backends propios — solo Prompt API on-device.
