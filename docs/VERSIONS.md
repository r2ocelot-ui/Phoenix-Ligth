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

Acumulado hasta 2026-06-11. Todo pasa 104/104 tests + smoke + JS lint.
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

### ✅ Hecho — 🧪 a falta de tu visto bueno (👁️)
| Bloque | Estado | Qué probar |
|---|---|---|
| Multi-tenant en `/cabinets/{id}/relay`, `/dim`, `/emergency/all-on` | 🧪 | Un operador de Madrid no debe poder tocar cuadros de Barcelona (404, sin leak) |
| WebSocket `/ws` valida usuario + permiso + scope | 🧪 | Desactivar un usuario → su WS se cierra; un user de Madrid solo ve sus cuadros en el snapshot |
| Guard de producción del `jwt_secret` | 🧪 | Arrancar con `PHOENIX_DEMO_MODE=false` y `jwt_secret` por defecto → revienta el arranque |
| `tools/make_release.py` (paquete limpio estilo Hydra) | 🧪 | `python3 tools/make_release.py` → `dist/phoenix-cliente-<fecha>.zip` sin `.git/.venv/.db/tests` |
| `services/sun.py` + endpoint `/cabinets/{id}/sun` | 🔵 | **Verificado 13-jun**: `/sun` de CAB-001 da amanecer 04:45 UTC (06:45 Madrid) — correcto, offline |
| Tarifa por tramos → dimming por coste (`services/tariff.py` + `/tariff`) | 🧪 | `GET /tariff/now` y `/schedule`; recorta dimming en punta sin bajar del mínimo de seguridad |
| **V1.R1.P1** · Bug TZ de la tarifa corregido (`tariff_timezone` + `zoneinfo`) | 🧪 | UTC→hora local; en un server UTC los tramos ya NO salen 2 h corridos |
| Encendido automático astronómico, **sin fotocélula** (`/cabinets/{id}/auto-level`) | 🧪 | `sun.py` decide ON/OFF + perfil + tope de tarifa. De día→0, de noche→nivel |
| Licencia **Ed25519** + `LICENSE`/`EULA` + `GET /license` (`tools/make_license.py`) | 🧪 | keygen→sign→verify; cliente solo lleva clave pública. Off por defecto |
| Tarifa: **topes configurables** (`tariff_cap_punta/llano/valle`) | 🧪 | Ajustables por contrato vía settings; `GET /tariff/now` los refleja |
| **MQTT seguro de ejemplo** (`infra/mosquitto.prod.conf`) | 🧪 | TLS + auth + ACL por cuadro, sin tocar el demo (anónimo) |
| **Cabeceras de seguridad** HTTP (nosniff, Referrer-Policy, X-Frame-Options) | 🧪 | `GET /health` las devuelve; no rompen el render |
| Fix: botón **"+ Nuevo rango"** abría en blanco | 🧪 | Permisos → Rangos → "+ Nuevo rango" ahora abre el formulario |
| Rangos muestran su **nombre** (Director / Phoenix), no el id interno | 🧪 | Tabla de usuarios, ficha y topbar |
| Username **capitalizado** al mostrar (pepe→Pepe) + **login case-insensitive** | 🧪 | Crea "pepe", se ve "Pepe"; entra con pepe/Pepe/PEPE |
| Migración: usuario **`admin` heredado → `phoenix`** (si no hay phoenix) | 🧪 | BD vieja: el owner vuelve a ser phoenix con id 1, sin perder datos |
| UI: **asignar usuario a proyecto** (+ `project_id` expuesto → arregla el contador que daba 0) | 🧪 | Permisos → desplegar usuario → selector "Proyecto / ciudad" |
| Alta de proyecto: **autocompletar ciudad/CP** (Nominatim forward) | 🧪 | Buscar "Benidorm" o un CP → rellena nombre + sugiere código |
| **Multi-proyecto (N:N)**: un usuario cubre **varias ciudades** (cualquier rango) | 🧪 | Permisos → desplegar usuario → **casillas** de ciudades. Ve los cuadros de TODAS sus ciudades; el rango limita *qué* hace, los proyectos *dónde* |
| Migración admin id 1 → phoenix (conserva id) + multi-proyecto desde project_id | 🧪 | Reiniciar backend: admin viejo pasa a phoenix con su id |
| **Admin resetea/quita contraseña, PIN y patrón** + **regenera claves 2FA** (sin desactivar el 2FA) | 🧪 | Permisos → desplegar usuario → botones; solo sobre rangos **estrictamente inferiores** |
| 🔒 Fix de escalado: resetear credenciales ahora exige rango inferior | 🧪 | Antes un admin_proyecto podía resetear la contraseña del owner |
| Fix: `/projects` devuelve TODAS las ciudades del usuario (multi-proyecto) | 🧪 | Un director con varias ciudades las ve todas en el selector |
| Fix: **asignar CM a ciudad/proyecto** (antes los CM globales los veían todos) | 🧪 | Editar CM → selector "Ciudad / proyecto"; nuevo CM hereda la ciudad activa |
| **Etiqueta de versión/build** en panel (sidebar + login) | 🧪 | `Light · vX · build <hash>`; sale del commit. Si no cuadra, recarga Ctrl+F5 |

### 📋 Pendiente — todo lo que queda (X)
Lista única de lo que falta. Al cerrarse, un bloque sube a **✅ Hecho** (🧪)
y luego a **🔵** con tu visto bueno. Es la única lista que hay que mirar.

**🔴 Investigar si reaparece**
- **Rectángulo negro en el mapa** (zoom concreto, no a otros niveles). No se
  vio nada en el código que lo dibuje → probable **tile de OSM fallido**.
  Si vuelve a salir fijo en el mismo sitio, Faro lo mira a fondo.
- Si tu BD tiene **a la vez** `admin` (viejo) y `phoenix`: la migración no
  toca nada (hay phoenix). Borra el `admin` sobrante a mano desde Permisos →
  Usuarios, o arranca con `phoenix.db` limpio.

**🟡 Prioritario**
| Bloque | Qué falta / por qué |
|---|---|
| Token JWT → cookie `HttpOnly` | hoy un XSS roba el token de `localStorage`. **⏸️ contigo delante**: toca el login y añade CSRF; no se hace a ciegas |
| Token del WebSocket fuera de la URL | acaba en logs → ticket efímero. **⏸️ contigo delante**: toca el login del WS, hay que probarlo en navegador |
| Completar datos legales `LICENSE`/`EULA` | Angel Eduardo ✓ · Kumiho ✓; **faltan contacto, localidad de jurisdicción y forma jurídica** (S.L.…) — los pones tú |
| Licencia: modo de enforcement (suave/intermedio/duro) | **decidido: suave por ahora**; al activar, preferible **intermedio** (periodo de gracia). Cambiarlo es trivial |
| Tarifa: **TRAMOS** configurables por proyecto | topes ✓ (hechos hoy); falta que el horario punta/valle sea por proyecto (hoy 2.0TD fijo) |
| MQTT en producción: aplicar `infra/mosquitto.prod.conf` | el ejemplo endurecido ✓; falta desplegarlo con certs reales (no toca al demo) |
| Pegar `docs/HYDRA-SECURITY-NOTES.md` en la sesión de Hydra | y aplicar su checklist allí |
| ESIOS/REE — precio kWh en tiempo real | dimming por coste real (detalle en *Integraciones*) |

**🟢 No urgente**
| Bloque | Qué falta / por qué |
|---|---|
| Cablear el auto-level a auto-dimming real (con override) | hoy es **asesor**; validar niveles en pantalla antes de darle las llaves |
| **Dimming adaptativo por uso de la calle** (idea del capitán) | (a) perfil de uso por punto/cuadro *offline*: calles tranquilas más bajas, vías principales más altas; (b) dinámico por evento (presencia/tráfico→sube, accidente→máx) vía bus Smartcity/Argus. Une #4 + #6 + V2 |
| Mover lógica crítica al servidor (modelo híbrido) | la protección anti-ingeniería-inversa real |
| **Multi-proyecto FASE 2**: jerarquía zona→ciudad | regiones que agrupan ciudades (director asignado a "Levante" ve todas sus ciudades sin marcarlas una a una). Hoy se cubre marcando varias; esto es la elegancia para zonas grandes |
| PBKDF2 → Argon2id | mejora del hashing. **⏸️ contigo**: migra credenciales + dependencia nativa nueva; con doble-formato de verificación |
| Cifrar `totp_secret` en BD | hoy se guarda en claro (toca el 2FA; lo hago con backward-compat cuando digas) |
| SQLite → Postgres + Alembic | para producción de verdad (**infra**: Postgres no disponible aquí) |
| CSP estricta en `index.html` | defensa fuerte anti-XSS. **⏸️**: requiere externalizar el JS inline primero, o rompe el panel |
| Limpiar `innerHTML` con datos dinámicos | pasar progresivamente a `textContent` |
| Fases lunares offline · AEMET | marginales (detalle en *Integraciones*) |

**👁️ Pendiente de TU verificación visual**
- Toda la tabla de **V1 — Base operativa** (arriba) y lo **✅ Hecho** de V1.R1:
  están 🧪 (Faro OK), faltan tus ojos para pasar a 🔵.

**⚪ Aparcado (no hacer salvo que cambie la decisión)**
- Telemetría de fotocélula → vamos **sin sensor** (encendido astronómico `sun.py`).
- **V2 · Ecosistema Smartcity** y su bus MQTT → es salto de versión, va más adelante.

### Integraciones externas candidatas (curado por Faro)
Criterio: que aporte valor REAL al alumbrado y no meta dependencias
frágiles. Lo offline siempre gana a lo que necesita internet.

| Integración | Estado | Por qué |
|---|---|---|
| **Tarifa eléctrica por tramos (P1/P2/P3) offline** | 🔵 | **Hecho** (`tariff.py` + `/tariff` + dimming coste-consciente) |
| **ESIOS/REE — precio kWh en tiempo real (España)** | 🟡 | Dimming inteligente por coste real (valle 100% / pico 80%). Gratis con registro. La única API externa que cambia la cara a Phoenix |
| **Bus Smartcity-1 (MQTT compartido Phoenix/Hydra/Argus/Osiris)** | 🟡 | Ver sección dedicada abajo |
| **Telemetría de fotocélula (sensor lux) en el CM** | ⚪ | Descartada de momento: el capitán va **sin fotocélula** (encendido astronómico con `sun.py`). Solo si se quiere validación cruzada |
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
