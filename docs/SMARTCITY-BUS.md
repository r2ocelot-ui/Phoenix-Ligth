# Smartcity-1 · Contrato del bus de eventos común

> El "alma común" del ecosistema. Cada producto es **autónomo** (se vende
> solo), pero cuando coinciden en el mismo despliegue municipal se enteran
> de lo que hacen los demás a través de **un bus de eventos MQTT
> compartido** y reaccionan. Acoplas *mensajes*, no *código*.
>
> Este documento es la fuente de verdad del contrato. **Pásalo a cualquier
> sesión** (Hydra, Argus, Osiris…) para que implemente su mitad igual.

## Estado honesto (no vender humo)
- **Phoenix** ya habla MQTT (su propio `phoenix/...`), así que el
  **transporte está listo**; la capa `smartcity/...` es un módulo pequeño
  pendiente. Estado: 🟡 no construido aún.
- **Hydra** hoy usa WebSockets internos; necesita **añadir un cliente
  MQTT** para conectarse al bus. Estado: 🟡 no construido aún.
- El resto (Argus, Osiris…) **nacerían ya hablando** Smartcity-1.

Diseñado, no hecho. Primero se cierra Phoenix R2; luego se valida el bus
con la pareja **Hydra ↔ Phoenix** (el "hola mundo" del ecosistema).

---

## La constelación

| Producto | Vertical | Rol en el bus | Estado |
|---|---|---|---|
| **PHOENIX** 🔥 | Alumbrado / Lighting | Sube luz ante eventos; publica fallos de red | Vivo |
| **HYDRA** 🐍 | Tráfico / Semáforos | Ámbar fail-safe; publica accidentes | Vivo (otra sesión) |
| **ARGUS** 👁️ | Vigilancia / Visión | "Los ojos": detecta y publica; enfoca cámaras | Idea |
| **OSIRIS** ♻️ | Basura / Residuos | Genera tareas de limpieza/recogida | Idea |
| **CERNUNNOS** 🌿 | Medioambiente | Aire, ruido, meteo; dispara reacciones | Idea |
| **ATHENA** 🦉 | Formación | Entrena con escenarios reales/simulados | Idea |
| **VULCAN** ⚒️ | Hardware | Provisión/firmware de dispositivos de todos | Idea |
| **ATLAS** 🗺️ | Infraestructura | Red, servidores, salud de la plataforma | Idea |
| **ORION** 🏹 | Control | "Panel único": consume TODO, orquesta, manda | Idea |

> **ORION** es especial: es la *sala de control* que ve todos los eventos
> de todos los verticales (single pane of glass) y puede emitir órdenes
> (`emergencia`). Es el consumidor universal del bus.

---

## Transporte

- **Un broker MQTT compartido** para todo el despliegue (Mosquitto/EMQX).
  No es el broker interno de cada producto: es el bus **inter-sistemas**.
- **TLS obligatorio** (`mqtts://`, 8883). 
- **Auth + ACL por producto**: cada uno tiene su usuario y solo puede
  publicar/suscribirse a los topics que le tocan (ver matriz).
- QoS **1** para eventos (al menos una entrega; los consumidores son
  idempotentes por `id`).

### Espacio de nombres
```
smartcity/eventos/<tipo>            # eventos transversales (lo que reacciona)
smartcity/estado/<source>/<rec>     # estado/telemetría compartida (retained)
smartcity/_presencia/<source>       # heartbeat (retained) → Orion ve quién vive
```

---

## El sobre (envelope JSON)

Todos los mensajes de `smartcity/eventos/*` comparten esta forma:

```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "source": "argus",
  "type": "obstaculo",
  "ts": "2026-06-10T22:14:00Z",
  "severity": "low | medium | high | critical",
  "location": { "lat": 40.4168, "lon": -3.7038, "zone": "Centro", "ref": "CAB-001" },
  "ttl_s": 300,
  "data": { }
}
```

- `id` — UUID v4. Los consumidores **deduplican** por `id` (idempotencia).
- `source` — quién publica (`phoenix`, `hydra`, `argus`…).
- `ts` — ISO-8601 UTC.
- `location.ref` — opcional, ata el evento a un recurso conocido (un CM,
  un cruce…). `zone` permite reaccionar por área sin coordenadas exactas.
- `ttl_s` — caducidad lógica; pasado ese tiempo el evento se ignora.
- `data` — payload específico del `type`.

---

## Catálogo de eventos núcleo

| `type` | Publica típico | Significado |
|---|---|---|
| `obstaculo` | Argus, Osiris | Basura/escombro/objeto en la vía |
| `accidente` | Hydra, Argus | Colisión/incidente en cruce o vía |
| `fallo_red` | Phoenix | Fallo eléctrico de alumbrado en zona |
| `intrusion` | Argus, Phoenix | Apertura no autorizada de CM/armario |
| `aglomeracion` | Argus | Concentración inusual de personas |
| `contenedor_lleno` | Osiris | Contenedor al límite → recoger |
| `calidad_aire` | Cernunnos | Episodio de contaminación/ruido |
| `dispositivo_caido` | Vulcan, Atlas | Equipo de campo sin heartbeat |
| `emergencia` | Orion (o manual) | Modo emergencia declarado en una zona |

---

## Matriz publica / reacciona (cercano)

| Producto | Publica | Reacciona a (se suscribe) |
|---|---|---|
| **Phoenix** | `fallo_red`, `intrusion` | `accidente`, `obstaculo`, `emergencia` → sube dimming / all-on en la zona |
| **Hydra** | `accidente`, `fallo_semaforo` | `fallo_red`, `obstaculo`, `emergencia` → ámbar intermitente fail-safe |
| **Argus** | `obstaculo`, `accidente`, `intrusion`, `aglomeracion` | `emergencia` → enfoca y graba cámaras de la zona |
| **Osiris** | `contenedor_lleno` | `obstaculo` (si es basura) → crea tarea para operario |
| **Orion** | `emergencia`, órdenes | **todo** (panel de control universal) |

> Los cross-cutting (**Vulcan** hardware, **Atlas** infra, **Cernunnos**
> medioambiente, **Athena** formación) tienen rol por concretar cuando se
> arranquen; encajan en el mismo sobre.

### Ejemplo de flujo
```
Argus ve basura en la vía
  → publica smartcity/eventos/obstaculo {severity:"medium", location:{...}}
        ├─ Phoenix sube dimming al 100% en esa zona (seguridad)
        ├─ Osiris crea tarea de limpieza para el operario más cercano
        └─ Hydra (si es un cruce) pone ámbar intermitente
```

---

## Cómo implementa cada uno su mitad

### Phoenix (este repo) — 🟡 pendiente
Ya tiene el cliente MQTT (`app/core/mqtt_client.py`, el `bus`). Falta un
módulo fino `services/smartcity.py` que:
- **Publique**: cuando el motor de alarmas detecte fallo eléctrico →
  `smartcity/eventos/fallo_red`; cuando salte intrusión de armario →
  `smartcity/eventos/intrusion`.
- **Se suscriba** a `smartcity/eventos/{accidente,obstaculo,emergencia}`
  → resolver la zona/CM por `location` y subir dimming/all-on (reusando
  la lógica de `control.py`, pero con guardarraíl: ver Seguridad).

### Hydra (otra sesión) — 🟡 pendiente
Añadir un cliente MQTT (`mqtt`/`mqtt.js`) al backend Node:
- **Publique**: en `safety.js`/`server.js`, al entrar en safe-mode o
  detectar conflicto → `smartcity/eventos/accidente` o `fallo_semaforo`.
- **Se suscriba** a `smartcity/eventos/{fallo_red,obstaculo,emergencia}`
  → mapear a la fase "todo ámbar intermitente" (que la matriz de
  conflictos ya permite) en los cruces de esa `zone`.

---

## Seguridad del bus (no opcional)

Un evento `accidente`/`emergencia` **dispara acciones físicas** (subir
luz, ámbar). Eso es poderoso → es un vector de abuso. Reglas:

1. **Broker autenticado + TLS + ACL por producto.** Nadie publica
   `emergencia` salvo Orion/operador autorizado.
2. **Validar el `source`** contra el topic (un productor no puede
   suplantar a otro: ACL por topic).
3. **Guardarraíl en la reacción**: las acciones críticas (all-on masivo)
   piden `severity:"critical"` + corroboración (p. ej. dos fuentes, o
   confirmación humana) — no un solo mensaje suelto.
4. **Rate-limit** por `source` y `type` para que un productor comprometido
   no inunde el bus.
5. **Auditar** todo evento recibido y toda reacción disparada (en Phoenix,
   vía `audit_log`).

> Sin esto, "accidente→all-on" se convierte en "cualquiera apaga/enciende
> la ciudad". El bus es tan crítico como el resto del sistema.

---

## Orden recomendado (anti-dispersión)
1. 🔵 Cerrar **Phoenix R2** (lo 🔴/🟡 de `VERSIONS.md`).
2. 🟡 Congelar **este contrato** (revisarlo entre Phoenix y Hydra).
3. 🟡 Implementar las **dos mitades Hydra ↔ Phoenix** con UN evento
   (`fallo_red` → ámbar) como prueba de fuego.
4. 🟢 Argus, luego Osiris, luego el resto — cada uno nace hablando esto.
