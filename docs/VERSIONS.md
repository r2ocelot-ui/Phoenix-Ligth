# Phoenix-Light · Versiones y revisiones

Registro de **versiones (Vx)** y **revisiones (Rx.y)**. Un bloque solo se
marca **🔵 OK** cuando el capitán lo ha probado en pantalla y funciona.
Hasta entonces queda 🧪 (verificada por Faro: tests + smoke + lint) o
🔨 (en curso).

## Cómo verificamos (doble visto bueno)
Cada bloque necesita **las dos** verificaciones para pasar a 🔵 OK:
1. 🧪 **Faro**: tests backend + smoke de endpoints + lint de JS.
2. 👁️ **Capitán**: lo prueba en pantalla y confirma que se ve y funciona.

Si ambas salen bien → 🔵 OK. Si una falla → se queda 🩹 con notas hasta
arreglarlo.

## Leyenda de prioridad / estado
- 🔴 **Urgente** — agujero real o bug crítico. Se hace ya.
- 🟡 **Prioritario** — importante para el siguiente hito, sin sangrar.
- 🟢 **No urgente** — hay que hacerlo, pero no bloquea nada.
- 🔵 **Completado** — Faro 🧪 + Capitán 👁️. Cerrado.
- 🔨 **En curso** — se está construyendo.
- 🧪 **Faro OK** — pasa tests/smoke/lint, falta visto bueno del capitán.
- 🩹 **Con notas** — funciona pero hay ajustes pendientes (se listan).

> Faro NO puede ver el render del navegador: valida código y backend.
> La verificación visual la hace siempre el capitán.

## Nomenclatura (versión / revisión / parche)
Versionado semántico estilo `V.R.P`, coherente con Hydra (`V8.3-R39`):
- **V — Versión** (mayor): cambia *qué es* el producto; puede romper
  compatibilidad. Ej.: `V1` (plataforma de alumbrado), `V2` (ecosistema).
- **R — Revisión** (menor): función nueva, mejora o endurecimiento, sin
  romper nada. Ej.: `V1.R1` (hardening sobre V1).
- **P — Parche**: solo repara un fallo, sin funcionalidad nueva.
  Ej.: `V1.R1.P1`.

Formato `V{n}.R{n}.P{n}`, omitiendo los ceros de cola: `V1` = `V1.R0.P0`;
`V1.R1` = primera revisión; `V1.R1.P1` = un arreglo sobre ella.

> Regla simple: ¿cambia *qué es*? → **V**. ¿lo mejora/añade sin romper?
> → **R**. ¿solo arregla un fallo? → **P**.

---

## V1 — Base operativa completa  ·  🧪 pendiente de verificación visual

Acumulado hasta 2026-06-10. Todo pasa 84/84 tests + smoke + JS lint.
Pendiente de que el capitán confirme en pantalla cada bloque:

| Bloque | Estado | Qué probar |
|---|---|---|
| Login 2 pasos (usuario+contraseña+PIN → patrón) | 🧪 | Entrar con phoenix/phoenix123/1234 + patrón 01258 |
| 2FA TOTP (Google Authenticator) | 🧪 | Menú usuario → "Mi 2FA" → escanear/clave → código |
| Anti-keylogger (cambiar credencial pide la actual) | 🧪 | Cambiar PIN/patrón |
| Anti-sabotaje (IP ban, siege, dispositivos) | 🧪 | Sección Seguridad |
| 7 rangos editables (Phoenix/Director/…) | 🧪 | Permisos → Rangos |
| Ficha del trabajador (4 packs + edición inline) | 🧪 | Permisos → desplegar usuario → ✎ Editar ficha. El demo `phoenix` ya viene relleno |
| Multi-tenant (cada Director ve solo su ciudad) | 🧪 | Crear proyecto + asignar |
| Inicio estilo Hydra (mapa + controles abajo) | 🧪 | **Mirar layout: leyenda al lado, herramientas+KPIs en fila** |
| Usuario arriba-derecha + reloj | 🧪 | Topbar |
| Ciudad flotante en el mapa (no la tapa el +/−) | 🧪 | Esquina del mapa |
| Herramientas mapa: ➕CM ➕Luminaria ✥Mover ✏Editar 🗑Eliminar | 🧪 | Caja de herramientas |
| Pestaña Luminarias (inventario) | 🧪 | Menú → Luminarias |
| Editor topología (CM/circuitos/luminarias) | 🧪 | Topología → clic CM |
| Ficha RF Light GEO (6 secciones, GPS, autocompletado) | 🧪 | Crear/editar luminaria |
| Pestaña Dispositivos (vinculación SICE) | 🧪 | Editor CM → Dispositivo |
| Pestaña Proyectos (solo Phoenix) | 🧪 | Permisos → Proyectos |
| Telemetría infra (temp/puerta/intrusión) | 🧪 | Cuadros + popup CM |
| Alarmas (eléctricas + físicas + consumo) | 🧪 | Dejar correr el demo |
| Dock de eventos (abajo derecha) | 🧪 | Esquina inferior |

**Cómo marcar OK:** cuando pruebes un bloque y vaya bien, dímelo
("el login OK", "la topología OK"…) y lo paso a 🔵 aquí. Cuando todos
estén 🔵, cerramos **V1** y la revisión **V1.R1** pasa a ser lo activo.

---

## V1.R1 — Hardening de seguridad y release  ·  🧪 en marcha

### 🔴 Hecho hoy
| Bloque | Estado | Qué probar |
|---|---|---|
| Multi-tenant en `/cabinets/{id}/relay`, `/dim`, `/emergency/all-on` | 🧪 | Un operador de Madrid no debe poder tocar cuadros de Barcelona (404, sin leak) |
| WebSocket `/ws` valida usuario + permiso + scope | 🧪 | Desactivar un usuario → su WS se cierra; un user de Madrid solo ve sus cuadros en el snapshot |
| Guard de producción del `jwt_secret` | 🧪 | Arrancar con `PHOENIX_DEMO_MODE=false` y `jwt_secret` por defecto → revienta el arranque |
| `tools/make_release.py` (paquete limpio estilo Hydra) | 🧪 | `python3 tools/make_release.py` → `dist/phoenix-cliente-<fecha>.zip` sin `.git/.venv/.db/tests` |
| `services/sun.py` + endpoint `/cabinets/{id}/sun` | 🧪 | Sunrise/sunset astronómico OFFLINE para sanity-check de la fotocélula |
| Tarifa por tramos → dimming por coste (`services/tariff.py` + `/tariff`) | 🧪 | `GET /tariff/now` y `/schedule`; recorta dimming en punta sin bajar del mínimo de seguridad |

### 🟡 Pendiente — primero mañana
| Bloque | Estado | Qué pasa |
|---|---|---|
| ⏰ **Bug TZ en tarifa**: usa la hora del servidor (`datetime.now()`) | 🟡 | Si el server va en UTC, los tramos salen 2 h corridos. Fijar `tariff_timezone` (`zoneinfo`, sigue offline). Parche **V1.R1.P1** |
| Telemetría de fotocélula (sensor lux) en CM | 🟢 | Reportar lectura + estado del sensor como el resto (voltaje, temp…). **Próximo paso natural tras `sun.py`** |
| Token JWT fuera de `localStorage` → cookie HttpOnly | 🟡 | Hoy un XSS roba el token |
| Token del WebSocket sale por URL | 🟡 | Acaba en logs de proxies. Migrar a ticket efímero o subprotocolo |

### 🟡 Anti-copia / convertir en producto
| Bloque | Estado | Qué pasa |
|---|---|---|
| `licensing.py` cableado + `config.py` con `license_*` | 🟡 | Hoy si lo usas peta (faltan settings) |
| Migrar HMAC → Ed25519 en licensing | 🟡 | Documentado en DECISIONS, pendiente |
| `LICENSE` + EULA en la raíz | 🟡 | Sin él, no hay palanca legal |
| MQTT TLS + auth + ACL por cuadro | 🟡 | Hoy `allow_anonymous true` |
| Mover lógica crítica al servidor (modelo híbrido) | 🟢 | La protección anti-RE real |

### 🟢 Hardening continuo
| Bloque | Estado | Qué pasa |
|---|---|---|
| PBKDF2 → Argon2id | 🟢 | Mejora, no urgente |
| Cifrar `totp_secret` en BD | 🟢 | Hoy se guarda en claro |
| SQLite → Postgres + Alembic | 🟢 | Para producción de verdad |
| CSP estricta en `index.html` | 🟢 | Defensa contra XSS |
| Limpiar `innerHTML` con datos dinámicos | 🟢 | Cambiar progresivamente a `textContent` |

### Hydra (pendiente, otra sesión)
| Bloque | Estado | Qué hacer |
|---|---|---|
| Pegar `docs/HYDRA-SECURITY-NOTES.md` en la sesión de Hydra | 🟡 | Y aplicar checklist allí |

### Integraciones externas candidatas (curado por Faro)
Criterio: que aporte valor REAL al alumbrado y no meta dependencias
frágiles. Lo offline siempre gana a lo que necesita internet.

| Integración | Estado | Por qué |
|---|---|---|
| **Tarifa eléctrica por tramos (P1/P2/P3) offline** | 🟡 | Dimming por coste con config local. **Cero red, cero API, mucho valor.** Primero esto |
| **ESIOS/REE — precio kWh en tiempo real (España)** | 🟡 | Dimming inteligente por coste real (valle 100% / pico 80%). Gratis con registro. La única API externa que cambia la cara a Phoenix |
| **Bus Smartcity-1 (MQTT compartido Phoenix/Hydra/Argus/Osiris)** | 🟡 | Ver sección dedicada abajo |
| **Telemetría de fotocélula (sensor lux) en el CM** | 🟢 | Pareja natural de `sun.py`: lux real + sanity-check astronómico |
| **Fases lunares offline** | 🟢 | Astronomía pura, junto a `sun.py`. Ajustaría el margen de encendido. Coste cero, valor marginal |
| **AEMET (meteo oficial España, clave gratis)** | 🟢 | El clima per se aporta poco al alumbrado; solo si surge un caso claro |

**Descartadas (humo — no volver a proponer):**
- APIs de "IA" genéricas → dependencia sin valor claro.
- Google Maps / Geocoding de pago → **ya cubierto** por Leaflet + OSM +
  Nominatim (geocoding inverso ya implementado en `reverseGeocode`).
- Open-Meteo / clima genérico → para alumbrado no aporta lo suficiente,
  y en red OT aislada ni siquiera llegaría.

---

## V2 — Ecosistema Smartcity-1 · 🌆 la visión "alma común"

> Salto de **versión** (no revisión): Phoenix deja de ser una plataforma
> aislada y pasa a ser un **nodo** que habla con los demás verticales.

Nueve verticales, **un solo bus de eventos**. Cada producto es
autónomo (se puede vender solo), pero cuando coinciden en el mismo
despliegue municipal se enteran de lo que hacen los demás y reaccionan.
**Contrato técnico completo en `docs/SMARTCITY-BUS.md`.**

| Producto | Vertical | Estado |
|---|---|---|
| **Phoenix** 🔥 | Alumbrado / Lighting | Vivo (este repo) |
| **Hydra** 🐍 | Tráfico / Semáforos | Vivo (otra sesión) |
| **Argus** 👁️ | Vigilancia / Visión | Idea |
| **Osiris** ♻️ | Basura / Residuos | Idea |
| **Cernunnos** 🌿 | Medioambiente | Idea |
| **Athena** 🦉 | Formación | Idea |
| **Vulcan** ⚒️ | Hardware | Idea |
| **Atlas** 🗺️ | Infraestructura | Idea |
| **Orion** 🏹 | Control (panel único, orquesta todo) | Idea |

### Cómo se hablan (patrón correcto)
Un **broker MQTT compartido** con namespace `smartcity/eventos/...`.
Cada producto **publica lo que pasa** sin saber quién escucha, y **se
suscribe** a lo que le interesa sin saber quién publica. Acoplas
mensajes, no código.

```
Argus ve obstáculo/basura → publica smartcity/eventos/obstaculo
     ├─→ Phoenix sube dimming en la zona (seguridad)
     ├─→ Osiris crea tarea para el operario (limpieza)
     └─→ Hydra ámbar intermitente si es en un cruce

Hydra detecta accidente → publica smartcity/eventos/accidente
     ├─→ Phoenix all-on alrededor (visibilidad para emergencias)
     └─→ Argus enfoca y graba las cámaras cercanas

Phoenix detecta fallo eléctrico → publica smartcity/eventos/fallo_red
     └─→ Hydra ámbar intermitente en los cruces afectados (fail-safe)
```

### Por qué esto es importante
Esto **no** es un capricho técnico: es lo que diferencia un producto
profesional ("plataforma Smartcity") de cuatro programas sueltos.
Es lo que venden ETRA, SICE o Telefónica como Smartcity Platform.
Y el coste de hacerlo bien desde el día 1 es **bajo**, porque solo
hay que definir un contrato de eventos JSON acordado.

### Orden recomendado (anti-dispersión)
🚨 **Construir las 4 cosas a la vez = pozo eterno sin producto.**

1. 🔵 **Phoenix V1 + V1.R1 completos** primero — terminar 🔴 y 🟡.
2. 🟡 **Definir contrato "Smartcity-1"** — doc corto con topics + JSON.
3. 🟡 **Hydra ↔ Phoenix se hablan** — primera prueba real del bus.
4. 🟢 **Argus** después — videovigilancia es un mundo (visión + RGPD).
5. 🟢 **Osiris** al final — logística + rutas.

Cada paso deja **algo vendible** antes de pasar al siguiente.

---

## Plantilla para próximas versiones / revisiones

```
## V{n} — {título}  ·  {estado}         ← salto grande (versión)
## V{n}.R{m} — {título}  ·  {estado}    ← mejora/endurecimiento (revisión)
## V{n}.R{m}.P{k} — {título}  ·  {estado} ← solo arreglo (parche)
Fecha · resumen.
| Bloque | Estado | Qué probar |
```
