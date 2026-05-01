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
