# TQ-Asistente sobre OpenFang (Módulo 3 — Ruta B)

Capa de **Agent OS** del proyecto. OpenFang (binario Rust) corre el agente
conversacional `tq-asistente` y el hand autónomo `collector-tq`, conectados a
**Telegram** y **WhatsApp** por sus puentes nativos, con el conocimiento
corporativo de TQ inyectado en su memoria de 6 capas. El stack FastAPI+LangGraph
del repo queda como entregable del Módulo 2 y como **fuente del conocimiento**
(`data/raw/*.json` + `apps/api/datos_estructurados.json`).

## Puertos y adaptadores (clean architecture)

OpenFang **ya implementa hexagonal** en la capa de canales: el **agente es el
núcleo (core)** y cada canal es un **adaptador** intercambiable, configurado por
datos (`config.toml`) sin tocar el agente. Los 40 channel adapters comparten un
mismo puerto (`trait ChannelAdapter`: `start`/`send`/`status`/`stop`).

```
   Telegram ──┐                         ┌────────────────────┐
   WhatsApp ──┤  adaptadores (puerto)   │  core: tq-asistente │ ── Ollama (qwen3:8b)
   (… 38 +) ──┘   [channels.*]  ───────▶│  + memoria 6 capas  │
                                        └────────────────────┘
```

Nuestra contribución se mantiene **separada y versionada** en este directorio
(config + agente + hand + env), sin código de transporte propio: añadir/quitar
un canal es editar `config.toml`. Ese es el límite limpio que pedíamos.

## Estructura

```
openfang/
  config.toml                 proveedor Ollama, canales Telegram+WhatsApp, bindings
  .env.example                tokens (copiar a .env, gitignored)
  agents/tq-asistente/agent.toml   agente conversacional (persona TQ + protocolo SENSIBLE), local qwen3:8b
  hands/collector-tq/         hand autónomo de inteligencia competitiva
    HAND.toml                 manifiesto: tools, settings TQ, playbook por fases, métricas de dashboard
    SKILL.md                  conocimiento de dominio (identidad TQ)
```

## Prerrequisitos (una vez)

```bash
curl -fsSL https://openfang.sh/install | sh     # binario macOS, SIN Rust
openfang --version && openfang doctor
ollama serve                                     # qwen3:8b + qwen3-embedding:0.6b ya descargados
git clone https://github.com/RightNow-AI/openfang ~/develop/openfang   # sólo para WhatsApp
cp openfang/.env.example openfang/.env           # y pon tu TELEGRAM_BOT_TOKEN (@BotFather)
```

## Runbook

```bash
openfang init            # crea ~/.openfang (una vez)
make of-config           # copia config + agente + hand a ~/.openfang
make of-start            # arranca el daemon → dashboard http://127.0.0.1:4200

# en otra terminal (con el daemon arriba):
make of-migrate          # inyecta KV (datos exactos) + corpus al vector store
make of-hand             # activa el Collector autónomo

# canales:
#   Telegram → ya activo con TELEGRAM_BOT_TOKEN en el .env; escríbele al bot.
make of-whatsapp         # arranca el gateway QR (3009); escanea el QR en el dashboard → Channels → WhatsApp

make of-status           # estado del daemon + del hand
```

## Verificación rápida

- `openfang doctor` en verde; Ollama detectado; dashboard en `:4200`.
- Chat: `openfang chat tq-asistente` → pregunta de producto/historia = respuesta
  fundamentada; pregunta sensible (retiro/litigio/salud) = redirige a canales
  oficiales sin confirmar/negar.
- Dashboard → el hand `collector-tq` muestra corridas, entidades y reportes.
- Telegram/WhatsApp: mensaje desde el teléfono → respuesta del agente.

## Notas

- **Modelo local (R1):** `qwen3:8b` para chat y para el hand. Si el Collector se
  queda corto en los loops agénticos, sube SÓLO su modelo en `hands/collector-tq/HAND.toml`
  (`[agent].model`) dejando el chat en 8b.
- **Pre-1.0 (R2):** anota `openfang --version` en el informe; puede haber cambios entre minors.
- **Hand custom (verificado en 0.6.9):** copiarlo a `~/.openfang/hands/collector-tq/`
  (lo hace `make of-config`) basta — OpenFang lo auto-carga y aparece en
  `openfang hand list`. Alternativa canónica: `openfang hand install openfang/hands/collector-tq`.
  Subcomandos reales: `list`, `active`, `activate`, `pause`, `resume`, `info`,
  `deactivate` (NO existe `hand status`).
- **Actualizar el agente:** cambiar `agent.toml` y re-aplicar requiere DELETE + POST
  del agente (no hay update de manifiesto en caliente). Si re-spawneas, re-etiqueta
  sus memorias al nuevo id o vuelve a correr `make of-migrate`.
- **Inyección al vector store:** OpenFang no expone REST de ingesta masiva; el
  script escribe en la tabla `memories` del SQLite de OpenFang (recall por LIKE).
  Ver `scripts/migrate_to_openfang.py`.
```
