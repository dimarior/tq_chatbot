# integrated-chat

Web Component de chat Q&A que corre entero en el navegador usando la API nativa de IA de Chrome (Prompt API + Gemini Nano on-device). Pensado para Tecnoquímicas como alternativa client-side al chatbot Python del repo principal.

> Cero costo de inferencia · cero latencia de red · datos del usuario nunca salen del navegador · integración con un solo tag.

Este es un sub-proyecto **independiente** del chatbot Python ubicado en `../tq_chatbot/`. No comparte código.

## Estructura

- **`component/`** — el Web Component reutilizable (`<company-chat></company-chat>`). Lo que la empresa adoptaría en producción.
- **`extension/`** — extensión Chrome MV3 que inyecta el componente sobre la web real de TQ, **solo para la demo**.
- **`demo/`** — página HTML standalone para probar el componente fuera de la extensión.

Detalles funcionales completos en [`SPEC.md`](./SPEC.md). Convenciones de desarrollo en [`CLAUDE.md`](./CLAUDE.md).

## Requisitos

- Chrome 138 o superior con Gemini Nano disponible.
- Flag habilitado: `chrome://flags/#prompt-api-for-gemini-nano` → `Enabled`.
- Primera vez: el navegador descarga el modelo (~2 GB). Después funciona sin red.

Verifica disponibilidad en la consola:

```js
await LanguageModel.availability()
// 'available' | 'downloadable' | 'downloading' | 'unavailable'
```

## Probar el demo standalone

Los módulos ES requieren ser servidos por HTTP (no `file://`). El server **debe** correr desde `integrated-chat/`, no desde `demo/`, porque la página importa `../component/index.js`:

```bash
cd integrated-chat
python3 -m http.server 8000
```

Abrir <http://localhost:8000/demo/>. Aparece una burbuja azul abajo a la derecha; click para abrirla.

## Cargar la extensión para la demo

1. `chrome://extensions/` → activar **Developer mode**.
2. **Load unpacked** → seleccionar `integrated-chat/extension/`.
3. Navegar a `https://www.tqconfiable.com/` o `https://www.tqfarma.com/`.

`extension/component` es un symlink a `../component` para mantener un solo árbol de fuentes. Si tu sistema no soporta symlinks (Windows con configuración por defecto), reemplázalo por una copia de la carpeta `component/`.

Si la burbuja no aparece y la consola muestra un error de CSP bloqueando `chrome-extension:`, ver `KNOWN_ISSUES.md` para la mitigación con `world: "MAIN"` content scripts.

## Batería de pruebas para la demo

Preguntas para validar la extensión sobre `https://www.tqconfiable.com/`. Empieza por las **verdes**: si esas funcionan, el flujo base está sólido.

### 🟢 Deberían responder (página actual o sitemap)

| # | Pregunta | Página esperada |
|---|---|---|
| 1 | ¿Qué hace Tecnoquímicas? | `/quienes-somos/quien-es-tq/` |
| 2 | ¿Cuál es la misión de TQ? | `/quienes-somos/mision/` |
| 3 | ¿Cuál es la visión de Tecnoquímicas? | `/quienes-somos/vision/` |
| 4 | ¿Qué dice el credo de la empresa? | `/quienes-somos/credo/` |
| 5 | ¿Cuándo se fundó Tecnoquímicas? | `/quienes-somos/historia/` |
| 6 | ¿Qué hace TQ por el medio ambiente? | `/mundo/planeta/` |
| 7 | ¿Cuáles son los beneficios de trabajar en TQ? | `/trabaja/beneficios/` |
| 8 | ¿Cómo contacto al servicio al cliente? | `/contacto/servicio-al-cliente/` |
| 9 | ¿Qué es la línea ética? | `/contacto/linea-etica/` |
| 10 | ¿Qué hay sobre gobierno corporativo? | `/gobierno-corporativo/` |

### 🟠 Sobre noticias específicas (validan el ranking semántico)

| # | Pregunta | Página esperada |
|---|---|---|
| 11 | ¿TQ lanzó alcohol gel MK? | `/noticias/tq-lanza-su-alcohol-gel-mk-al-70/` |
| 12 | ¿TQ es una multilatina? | `/noticias/tq-una-de-las-100-multilatinas/` |
| 13 | ¿Winny está entre las marcas más valiosas? | `/noticias/winny-una-de-las-20-marcas-colombianas-mas-valiosas/` |

### 🔴 Deberían fallar honestamente (`not-found`)

| # | Pregunta | Por qué |
|---|---|---|
| 14 | ¿Cuál es el sueldo del CEO? | Información no pública |
| 15 | ¿Cuántas acciones tiene la empresa? | Información no pública |
| 16 | ¿Cuál es el correo personal de Francisco Barberi? | Test anti-alucinación |

### ⚠️ Test del límite documentado (entity confusion)

| # | Pregunta | Comportamiento esperado |
|---|---|---|
| 17 | ¿Cuándo se fundó TQ Farma? | TQ Farma vive en `tqfarma.com`; en `tqconfiable.com` no hay info específica. Lo correcto sería `not-found`. Por el límite del modelo on-device documentado en [`KNOWN_ISSUES.md`](./KNOWN_ISSUES.md), puede confundir y devolver 1934 (la fecha de Tecnoquímicas, su matriz). Sirve para evidenciar el límite. |

Para reportar fallos: la pregunta exacta + la respuesta + screenshot del log expandido `[qa-orchestrator]` (chosen / primary / fallback).

## Uso en producción (visión)

Copiar la carpeta `component/` al sitio de la empresa y agregar el tag:

```html
<script type="module" src="/component/index.js"></script>
<company-chat sitemap-url="/sitemap.xml" accent-color="#0033A0"></company-chat>
```

## Documentación de Chrome Built-in AI

- [Prompt API](https://developer.chrome.com/docs/ai/prompt-api)
- [Built-in AI APIs (overview)](https://developer.chrome.com/docs/ai/built-in-apis)
- [Structured output](https://developer.chrome.com/docs/ai/structured-output-for-prompt-api)
- [Session management](https://developer.chrome.com/docs/ai/session-management)
