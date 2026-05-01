# Issues conocidos — `integrated-chat`

Este documento registra problemas observados en el subsistema de búsqueda y respuesta (orchestrator + dom-reader + sitemap + ai). Existe porque varios bugs visibles en el demo —que parecen distintos— comparten causa raíz, y un parche rápido a uno tiende a dejar otro al descubierto.

## Resumen de la evaluación arquitectónica

El stack es **sólido en sus capas inferiores** y **frágil en la decisión de relevancia**.

| Capa | Estado | Comentario |
|---|---|---|
| `dom-reader.js` | sólido | Extracción y chunking determinísticos. Probado contra el demo. |
| `sitemap.js` | sólido | Parser tolerante, ranking Jaccard, fetch con timeout y URL normalization. |
| `ai.js` | sólido tras fixes | Wrapper estable. La sesión es **stateless por clone** (un fix crítico de Capa 6). 4 estados de `availability()` cubiertos. |
| `qa-orchestrator.js` | **frágil** | Decide cuándo hacer fallback y cuál resultado elegir. Es donde se manifiestan los síntomas. |
| Modelo (Gemini Nano) | **fuera de nuestro control** | Pequeño (≤2 GB). Cumple instrucciones probabilísticamente, no de forma determinista. |

El cuello de botella está abajo del orchestrator: el modelo on-device es la fuente real de los bugs recurrentes. El orchestrator solo amplifica o filtra los errores del modelo.

## Patrón de bugs recurrentes

Cinco rondas de iteración han mostrado el mismo perfil:

| Ronda | Síntoma | Causa raíz | Fix aplicado |
|---|---|---|---|
| 1 | Burbuja no aparece | Server desde docroot equivocado | Comando del server |
| 2 | Ranking parece igual para todas las preguntas | `readPageForQuestion` no rankea cuando todo cabe en budget | Ajuste en debug button |
| 3 | Fallback no dispara | `rankUrls` filtra cuando no hay hits léxicos | Blind fallback como respaldo |
| 4 | Fallback prueba la página actual | URL no normalizada (`/demo/` ≠ `/demo/index.html`) | `normalizeUrl` |
| 5 | "Página actual" responde con texto que solo existe en otra página | Sesión no era stateless: prompts previos contaminaban siguientes | `session.clone()` por ask |
| 6 (actual) | Respuesta correcta sintácticamente pero sobre la entidad equivocada (TQ Farma → Tecnoquímicas) | Modelo conflata entidades parecidas, reporta `found=true conf=1.0` con info tangencial | **Sin fix — documentado** |

Los fixes 1-5 cierran bugs reales pero el patrón "el modelo dice found=true cuando no debería" sigue apareciendo. Cada parche reduce su frecuencia, no lo elimina.

## Issue principal abierto: confusión de entidades en respuestas

**Estado:** abierto. Aceptado como limitación conocida del modelo.
**Severidad:** media en demo standalone, baja-media esperada en demo con sitio real (Capa 7).

### Reproducción

1. Cargar `http://localhost:8000/demo/`.
2. Preguntar "¿Cuándo se fundó TQ Farma?".
3. Resultado actual: el bot responde con la fundación de **Tecnoquímicas** (1934, Jorge Garcés Borrero, Cali), citando `historia.html`. La pregunta era por la división TQ Farma, no por la compañía matriz.

### Cadena de causalidad

1. Pregunta contiene "TQ Farma". Ninguna página del demo tiene la fecha de fundación específica de TQ Farma como división.
2. Primary (`index.html`) → `found=false` o `found=true` con baja confianza.
3. Orchestrator dispara fallback. URLs no comparten tokens léxicos con la pregunta → `rankUrls` vacío → blind fallback prueba `historia.html` y `sostenibilidad.html`.
4. `historia.html` tiene contexto sobre fundación de Tecnoquímicas. El modelo lee la pregunta "¿cuándo se fundó TQ Farma?", asume **TQ Farma == Tecnoquímicas**, y reporta `found=true confidence=1.0` con la respuesta sobre Tecnoquímicas.
5. `_isBetter` prefiere fallback `found=true` sobre primary `found=false`. El usuario ve la respuesta equivocada.

El bug NO está en el código del orchestrator: hace lo que tiene que hacer (intentar fallback, elegir el mejor resultado). El bug está en el paso 4 — el modelo conflata entidades porque es pequeño y la instrucción "no menciones datos tangenciales" no le impide redefinir el sujeto de la pregunta.

### Por qué los parches anteriores no eliminan el patrón

| Parche aplicado | Por qué no es suficiente |
|---|---|
| Tightening del prompt (`found=true` requiere respuesta específica) | El modelo respeta la regla literal pero no detecta que cambió el sujeto de la pregunta |
| Override del answer cuando `found=false` | Solo limpia false-negatives, no false-positives con conf=1.0 |
| `session.clone()` para stateless | Quita contaminación entre llamadas pero no la confusión dentro de una sola |
| Blind fallback | Asegura cobertura pero también empuja al modelo a forzar conexiones donde no las hay |

### Mitigaciones posibles (no implementadas)

Listadas por relación costo/beneficio:

1. **Verificación de segundo paso (recomendado si hay que arreglarlo).**
   Tras `parsed.found===true`, hacer un prompt corto adicional:
   *"La pregunta del usuario fue: <Q>. La respuesta dada fue: <A>. ¿La respuesta menciona específicamente lo que pregunta el usuario? Devuelve solo `true` o `false`."*
   Si `false`, forzar `found=false`.
   - **Costo:** +1 prompt (~500-800 ms) por pregunta. Aumenta latencia visible.
   - **Beneficio:** ataca la causa raíz (calibración del modelo). El "segundo modelo" es el mismo, pero con foco distinto suele detectar la disonancia.

2. **Extracción de entidades de la pregunta + match literal en contexto.**
   Heurística: capturar palabras capitalizadas y siglas (`TQ Farma`, `MK`, `Tecnoquímicas`). Antes de aceptar `found=true`, verificar que el contexto contenga la cadena literal de la entidad.
   - **Costo:** trivial.
   - **Beneficio:** reduce false-positives donde el modelo conflata. Riesgo de false-negatives cuando el contexto usa sinónimos.

3. **Embeddings on-device para retrieval.**
   Cuando Chrome libere la API de embeddings on-device, reemplazar el ranking Jaccard por similarity coseno sobre embeddings.
   - **Costo:** mediano (depende del API).
   - **Beneficio:** mejora retrieval pero no resuelve la conflación dentro del modelo.

4. **Switch a cloud LLM con guardrails.**
   Rompe la narrativa "cero red, on-device" del proyecto. Solo si el cliente acepta.

### Decisión actual

**No implementar mitigaciones ahora.** Razones:

- El demo standalone usa páginas adversariales (`historia.html` habla de la matriz, no de la división) que maximizan la confusión. La presentación final usa el sitio real de TQ, donde:
  - URLs tienen slugs descriptivos (`/tq-farma`, `/sostenibilidad`, ...) → ranking léxico funciona → blind fallback no necesario.
  - Cada entidad tiene su página dedicada → menos colisiones de "TQ Farma vs Tecnoquímicas" porque cada uno tiene contexto auto-contenido.
  - Más contenido por página → más señal para que el modelo distinga.

- Tras Capa 7, si el patrón persiste en preguntas reales (no adversariales), evaluar mitigación #1 (verificación de segundo paso).

## Issue secundario: CSP del sitio bloquea la inyección del componente

**Estado:** abierto, hipotético — no observado aún en los sitios de TQ.
**Severidad:** alta si se materializa (la burbuja no aparece).

### Reproducción potencial

`extension/content.js` inyecta el componente via:

```js
const script = document.createElement('script');
script.type = 'module';
script.src = chrome.runtime.getURL('component/index.js');
document.head.appendChild(script);
```

Si el sitio anfitrión tiene un encabezado `Content-Security-Policy: script-src 'self'` (sin `chrome-extension:` ni `'unsafe-inline'`), Chrome bloquea el load del script. La consola del sitio mostrará un error CSP. La burbuja no se renderiza.

### Mitigación

Mover la inyección del componente a un content_script declarado con `"world": "MAIN"` en el manifest. Los scripts inyectados así por la extensión NO están sujetos al CSP del sitio.

Trade-off: los content_scripts en MAIN no tienen acceso a `chrome.runtime`, así que no pueden hacer `chrome.runtime.getURL`. Hay que pasar la URL desde un content_script ISOLATED via `window.postMessage` o setting un atributo en `<html>` que el script MAIN lea.

Esquema:

```json
"content_scripts": [
  { "js": ["content-isolated.js"], "matches": [...] },
  { "js": ["content-main.js"], "world": "MAIN", "matches": [...] }
]
```

```js
// content-isolated.js
document.documentElement.dataset.tqExtBase = chrome.runtime.getURL('').replace(/\/$/, '');
```

```js
// content-main.js
const base = document.documentElement.dataset.tqExtBase;
import(`${base}/component/index.js`).then(() => { ... });
```

No implementado aún porque añade complejidad innecesaria si los sitios de TQ no lo necesitan. Validar primero en presentación; si falla, aplicar.

## Issue secundario: warning "No output language was specified"

**Estado:** abierto, non-blocking.

Chrome imprime en consola por cada `session.prompt()`:

```
No output language was specified in a LanguageModel API request.
An output language should be specified to ensure optimal output quality
and properly attest to output safety. Please specify a supported output
language code: [es]
```

La sesión ya se crea con `expectedOutputs: [{type:'text', languages:['es']}]`, así que el modelo responde en español. El warning es de la API que prefiere el código repetido por llamada. Cuando Chrome documente la opción estable (`outputLanguage: 'es'` en el objeto de opciones de `prompt()`), agregarla en `ai.js`. Por ahora ignorable.

## Reglas para futuras correcciones en este subsistema

1. **Reproducir y trazar antes de parchar.** El log `[qa-orchestrator]` muestra primary, fallback y chosen — usar esto para identificar dónde falla.
2. **Clasificar la causa.** ¿Es (a) retrieval, (b) modelo, (c) post-procesamiento? Cada uno tiene fixes distintos.
3. **Si la causa es el modelo, aceptar que el fix es probabilístico.** No prometer determinismo donde no lo hay.
4. **Tabla de regresión.** Antes de mergear un parche, validar contra las preguntas conocidas:

   | Pregunta | Esperado | Página esperada |
   |---|---|---|
   | ¿Cuándo se fundó Tecnoquímicas? | found, año 1934 | current (index) |
   | ¿Quién fundó Tecnoquímicas? | found, Jorge Garcés Borrero | historia.html |
   | ¿Cuál es la meta de reducción de carbono? | found, 35% para 2030 | sostenibilidad.html |
   | ¿Qué medicamentos tiene la línea MK? | found, lista de MK | vademecum.html |
   | ¿Cuándo se fundó TQ Farma? | **not-found** (correcto) | sin fuente |
   | ¿Quién es el CEO actual? | not-found | sin fuente |

5. **No tocar el cuerpo de `_askWithRoot` o el schema de respuesta sin re-validar la tabla.** Los cambios al prompt o al schema afectan a todas las preguntas a la vez.
