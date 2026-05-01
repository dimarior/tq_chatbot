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

## Preguntas de prueba

Batería para validar la extensión sobre `https://www.tqconfiable.com/`. Empieza por las verdes: si esas funcionan, el flujo base está sólido.

### Deberían responder (página actual o sitemap)

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

### Sobre noticias específicas (validan ranking semántico)

| # | Pregunta | Página esperada |
|---|---|---|
| 11 | ¿TQ lanzó alcohol gel MK? | `/noticias/tq-lanza-su-alcohol-gel-mk-al-70/` |
| 12 | ¿TQ es una multilatina? | `/noticias/tq-una-de-las-100-multilatinas/` |
| 13 | ¿Winny está entre las marcas más valiosas? | `/noticias/winny-una-de-las-20-marcas-colombianas-mas-valiosas/` |

### Deberían fallar honestamente (`not-found`)

| # | Pregunta | Por qué |
|---|---|---|
| 14 | ¿Cuál es el sueldo del CEO? | Información no pública |
| 15 | ¿Cuántas acciones tiene la empresa? | Información no pública |
| 16 | ¿Cuál es el correo personal de Francisco Barberi? | Test anti-alucinación |

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
