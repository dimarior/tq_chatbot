# integrated-chat

Chatbot de Q&A para Tecnoquímicas que corre **enteramente en el navegador** usando la API nativa de IA de Chrome (Prompt API + Gemini Nano on-device). Empaquetado como Web Component (`<company-chat></company-chat>`); la demo se inyecta en la web real de TQ vía una extensión.

> Cero costo de inferencia · cero red para responder · datos del usuario nunca salen del navegador · integración con un solo tag.

## Habilitar Chrome Built-in AI

1. Usar Chrome **138 o superior**.
2. Abrir `chrome://flags/#prompt-api-for-gemini-nano` y ponerlo en **Enabled**.
3. Reiniciar Chrome.
4. Verificar en la consola del navegador (DevTools → Console):
   ```js
   await LanguageModel.availability()
   // 'available' → listo
   // 'downloadable' → descargar antes de la demo (~2 GB)
   // 'downloading' → en progreso
   // 'unavailable' → revisar versión / flag / hardware
   ```

La descarga del modelo es **una sola vez**. Después funciona sin red.

## Probar el demo en local

Los módulos ES requieren ser servidos por HTTP (no `file://`). El server **debe** correr desde `integrated-chat/`, no desde `demo/`, porque la página importa `../component/index.js`:

```bash
cd integrated-chat
python3 -m http.server 8000
```

Abrir <http://localhost:8000/demo/>. Aparece una burbuja azul abajo a la derecha; click para abrirla.

## Cargar la extensión sobre la web real de TQ

1. Abrir `chrome://extensions/` y activar **Developer mode** (toggle arriba a la derecha).
2. Click en **Load unpacked** y seleccionar `integrated-chat/extension/`.
3. Visitar `https://www.tqconfiable.com/` o `https://www.tqfarma.com/`.

`extension/component` es un symlink a `../component`. En sistemas que no soporten symlinks (Windows con configuración por defecto), reemplazar por una copia de la carpeta `component/`.

## Uso en producción

Para que la empresa adopte el componente en su sitio: copiar la carpeta `component/` y agregar el tag al HTML.

```html
<script type="module" src="/component/index.js"></script>
<company-chat sitemap-url="/sitemap.xml" accent-color="#0033A0"></company-chat>
```

Atributos opcionales: `position` (`bottom-right` · `bottom-left` · `top-right` · `top-left`), `placeholder`.

## Documentación de referencia

- [Prompt API](https://developer.chrome.com/docs/ai/prompt-api)
- [Built-in AI APIs (overview)](https://developer.chrome.com/docs/ai/built-in-apis)
- [Structured output](https://developer.chrome.com/docs/ai/structured-output-for-prompt-api)
- [Session management](https://developer.chrome.com/docs/ai/session-management)
