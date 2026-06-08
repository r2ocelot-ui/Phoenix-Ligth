# Phoenix-Light · Decisiones de diseño

Vivero de decisiones que se han ido tomando durante el desarrollo. Cada
decisión se anota con su fecha aproximada y el **porqué**, no sólo el
**qué** — para que el contexto sobreviva a los cambios de conversación.

---

## 1. Seguridad y autenticación

### 1.1 Login en dos pasos obligatorios (estilo Hydra) — 2026-06
- **Paso 1:** usuario + contraseña + PIN (una sola pantalla).
- **Paso 2:** patrón geométrico 3×3 estilo móvil.
- Entre ambos pasos se intercambia un **challenge token** firmado, con
  `step: 1` y caducidad **90 s**. Sólo sirve para consumir el paso 2.
- Cuentas sin patrón configurado terminan el login en el paso 1 — así
  un admin recién creado puede entrar y configurar el suyo desde dentro.

### 1.2 PIN y patrón son hashes del lado del servidor
- PBKDF2-SHA256, 200 000 rondas (mismo motor que la contraseña).
- Verificación **siempre** en backend. Nada se valida en el navegador.
- Esto es lo que diferencia Phoenix del Hydra revisado (que llevaba
  los PINs en texto plano dentro del bundle JS).

### 1.3 Anti-keylogger: rotar credencial requiere la actual
- `/auth/password`, `/auth/pin`, `/auth/pattern` exigen el valor actual
  para aceptar el nuevo. Único caso exento: cuando la credencial se
  define por primera vez (no había nada previo).
- Defensa real contra keyloggers pasivos: aunque te capturen las
  teclas, no pueden rotar la credencial sin la actual.
- El reset por admin (`/users/{id}/password`) **no** pide la actual —
  es un reset, no un cambio personal.

### 1.4 Bloqueo anti fuerza bruta
- Tras `PHOENIX_AUTH_MAX_FAILED_ATTEMPTS` fallos consecutivos
  (default **5**), la cuenta se bloquea `PHOENIX_AUTH_LOCKOUT_MINUTES`
  (default **5 min**) en el modelo (`User.locked_until`).
- Aplica a login (contraseña Y PIN) y a unlock (PIN/patrón). Durante
  el bloqueo, incluso la credencial correcta devuelve **HTTP 429**.
- Un login bueno **resetea el contador**.

### 1.5 Historial de seguridad (admin-only)
- Endpoint `/api/v1/audit/security` filtra eventos `auth.*` y
  `emergency.*` del audit log general. Requiere permiso `user:manage`.
- Vista "Seguridad" en el panel: KPIs de 24 h (logins OK / fallidos
  / lockouts) y feed con badges de color (verde / rojo / ámbar).
- El Supervisor sigue viendo `/audit` general; sólo Admin/Owner ve esto.

### 1.6 Defensa activa (anti-sabotaje) — 2026-06
Cuatro piezas que comparten infraestructura:

- **Rate-limit por IP + auto-ban** (`services/ip_guard.py`):
  tras `PHOENIX_IP_BAN_FAILED_THRESHOLD` (default **10**) fallos de login en
  `PHOENIX_IP_BAN_WINDOW_MINUTES` (default **10**) min, la IP queda baneada
  `PHOENIX_IP_BAN_DURATION_MINUTES` (default **30**) min. Persiste en BD.
- **Banlist gestionable** desde el panel de Seguridad: ver, banear a mano
  (con motivo y duración), quitar. Auditado.
- **Dispositivos del usuario** (`services/device_guard.py`): cookie
  `phoenix_device` opaca firmada por el servidor, lista de dispositivos
  conocidos. Login desde uno nuevo → evento `security.new_device` en el
  feed. El usuario ve sus dispositivos y puede revocar.
- **Modo Siege** (sólo Owner): cuando está ON, solo IPs whitelisted pueden
  entrar — todo lo demás recibe 403. Útil ante sabotaje en curso. El Owner
  añade/quita IPs whitelisted desde la pestaña de Seguridad.

El IP guard se aplica como dependencia a nivel router HTTP (no global ni
middleware) para que respete los overrides de `get_db` en los tests y
para que las rutas WebSocket — que no tienen `Request` — sigan funcionando.

### 1.7 Vinculación con hardware (estilo SICE PADRO) — 2026-06
Modelo `Device` (`cabinet_code`, `serial`, `imei`, `model`, `firmware`).
Endpoints `/api/v1/devices` para registrar/listar/desactivar. Cada cuadro
físico puede tener un controlador vinculado (uno activo a la vez).

El bus MQTT consulta `device_registry.allow_telemetry()` antes de aceptar
una medida: si el cuadro tiene un device vinculado y el `device_serial`
del payload no coincide → la medida se descarta y el intento queda como
`security.device_mismatch` en el feed. Telemetría sin `device_serial` se
acepta sólo si `PHOENIX_REQUIRE_DEVICE_SERIAL=false` (default), para no
romper la demo. Activarlo en producción una vez todos los cuadros estén
registrados.

### 1.8 Pendiente: 2FA TOTP estilo Google Authenticator
- Decidido en sesión 2026-06: lo añadiremos como **cuarta credencial**
  encima de contraseña + PIN + patrón, no en sustitución.
- Probablemente como tercer paso opcional, activable por usuario.
- Por hacer.

---

## 2. Roles y permisos

### 2.1 Jerarquía de 7 niveles (estilo Hydra) — 2026-06
Reemplaza el modelo plano anterior (`novato → owner`).

| Nivel | ID                | Para qué                                              |
|------:|-------------------|-------------------------------------------------------|
|     6 | `owner`           | Dueño del software Phoenix. Acceso total.             |
|     5 | `admin_proyecto`  | Admin de una ciudad / instalación. Sólo SU proyecto.  |
|     4 | `ingeniero`       | Responsable técnico: topología, cuadros, analítica.   |
|     3 | `supervisor`      | Jefe de turno: operación + alarmas + ver usuarios.    |
|     2 | `tecnico`         | Operario de campo: opera y reconoce alarmas.          |
|     1 | `operador`        | Sala de control: encender/apagar/regular.             |
|     0 | `visualizador`    | Sólo lectura (becarios, auditores externos).          |

Notas:
- `admin_programa` se valoró y se descartó: Owner ya cubre ese papel.
- Migración automática de rangos antiguos:
  `novato → visualizador`, `admin → admin_proyecto`.

### 2.2 Edición de roles
- Owner edita todos.
- `admin_proyecto` edita solo roles **estrictamente inferiores** al suyo
  (es decir hasta `ingeniero` incluido).
- Nadie puede asignar o promocionar a un rango ≥ al suyo propio.

### 2.3 Permisos ajustables por usuario
- El rol da el conjunto base. Encima, cada usuario puede tener
  `extra_permissions` (concesiones) y `denied_permissions` (denegaciones)
  que se aplican sobre el set base.
- Quien gestiona estos overrides es quien tenga `user:manage`.

### 2.4 Editor de rangos (catálogo en BD) — 2026-06
- Los 7 rangos por defecto se siembran en la tabla `roles` la primera vez
  que la base de datos está vacía. A partir de ahí son **editables**:
  un Owner o un admin de proyecto puede marcar/desmarcar los permisos de
  cada rango desde la pestaña **Rangos** del panel.
- También permite **crear rangos personalizados** (slug, label, descripción,
  nivel, set de permisos) — útiles para auditores externos, ingenieros
  júnior, etc.
- Reglas:
  - Owner es de solo lectura (siempre tiene wildcard).
  - Nadie puede editar un rango con nivel ≥ al suyo (no autoescalado).
  - Nadie puede otorgar a un rango un permiso que el editor no tenga.
  - No se borran rangos por defecto. Los custom solo si nadie los tiene
    asignado.
- Implementación: módulo `services/role_store.py` (CRUD + audit), router
  `api/v1/roles.py`, schemas en `schemas/role.py`. `ranks.RANKS` deja de
  ser una constante: pasa a ser un cache que `reload_ranks(db)` rehidrata
  desde la tabla tras cada edición. El resto del código consume `RANKS`
  exactamente como antes — la API interna no cambió.
- Nuevo permiso: `role:manage`, asignado por defecto a `admin_proyecto` y
  cubierto por el wildcard de `owner`. Sin él la pestaña Rangos sale como
  solo lectura (la podemos ver, no editar).

---

## 3. Multi-tenant

### 3.1 Activación del aislamiento multi-tenant — 2026-06
- Modelo `Project` (ciudad/instalación) en schema con `id`, `code`, `name`,
  `created_at`. `User.project_id` y `Cabinet.project_id` referencian al
  proyecto (NULL = "global"/sin asignar).
- **Filtrado activo** desde esta versión. Reglas:
  - **Owner** (wildcard `*`): ve todo. Tiene un chip "Ciudad" en la topbar
    que le permite filtrar manualmente a un proyecto (?project_id=X).
  - **Resto** (admin, ingeniero, supervisor, tecnico, operador, visualizador):
    locked a su `user.project_id`. Si es NULL → ve solo recursos NULL
    ("global"). Si es X → ve solo recursos con `project_id == X`.
  - Cuando un admin crea un usuario o cuadro, hereda automáticamente su
    propio `project_id`.
- Servicio `services/tenancy.py` centraliza la lógica: `scope_query()`
  para queries, `ensure_visible()` para detalle, `cabinet_codes_in_scope()`
  para endpoints que filtran por código (devices).
- Endpoints aplicando el filtro: `/users`, `/cabinets`, `/cabinets/registry`,
  `/devices`. `/auth/security` queda visible para admins (es global por
  diseño — registro append-only del sistema).
- Endpoint `/projects` con CRUD (POST/DELETE solo owner) + `assign-user`
  + `assign-cabinet/{code}`.
- En la UI, el chip de ciudad muestra el proyecto activo y, para owner,
  despliega un selector con todas las ciudades + "Todas las ciudades".
- Migración: la auto-migración añade `project_id` a `cabinets` sin
  romper datos existentes. El seed demo crea un proyecto "madrid"
  (Madrid Centro) y asigna los 4 cuadros demo a él.

---

## 4. UX adoptado de Hydra

### 4.0 PRINCIPIO RECTOR: Phoenix se maneja IGUAL que Hydra — 2026-06
Decisión de producto del capitán: Phoenix (alumbrado) y Hydra Traffic
(semáforos) deben **operarse de la misma forma**. Misma disposición,
mismos gestos, mismos controles. Así quien usa uno sabe usar el otro sin
reaprender; sólo cambia el dominio (luminarias vs semáforos).
- Mapa operativo como pantalla principal (Inicio).
- **Controles, herramientas y KPIs DEBAJO del mapa**, no encima: fila
  "colorear por" + barra de herramientas de edición + los 4 KPIs
  (Cuadros / Online / Alarmas / Potencia) + leyenda, todo bajo el mapa.
- Barra de herramientas de edición tipo Hydra (debajo del minimapa):
  "➕ Centro de mando", "➕ Luminaria", "✥ Mover".
- Al añadir clicando el mapa se captura la geolocalización (como RF
  Light GEO): la ficha llega con lat/lon + dirección ya rellenas.
- Regla práctica: ante una duda de UX, "¿cómo lo hace Hydra?" gana.

### 4.1 Modal de inactividad con cuenta atrás
- Aviso a -1 min, cuenta atrás visible los últimos 30 s con botón
  "Seguir trabajando".

### 4.2 Bloqueo manual de pantalla
- Botón 🔒 en sidebar → pantalla bloqueada con keypad y/o pantalla del
  patrón. Si el usuario tiene ambos, conmutador "Usar PIN / Usar patrón".

### 4.3 Modo Emergencia
- Botón ⚠ en sidebar (sólo `cabinet:control`) → `POST /emergency/all-on`
  enciende todo + 100% dim en un solo paso. Auditado.

### 4.4 Descripciones de rango en los selectores
- Cada rango lleva una descripción que se muestra en `<option title>` y
  como hint debajo del selector al crear usuarios.

---

## 5. Infraestructura

### 5.1 Auto-migración de columnas — 2026-06
- En `init_db()`, antes de servir, se hace inspección del schema y se
  ejecuta `ALTER TABLE ... ADD COLUMN` para cualquier columna que esté
  en el modelo pero no en la BD.
- Sólo añade. Nunca borra ni cambia tipo. Para cambios más profundos
  habrá que hacer Alembic — pero hoy no toca.
- Saca al usuario del bucle de "borra `phoenix.db` y vuelve a empezar"
  cada vez que crece el esquema.

### 5.2 Por qué Python (FastAPI) y no TypeScript — 2026-06
Decisión revisitada cuando una IA de búsqueda sugirió migrar el núcleo a
TypeScript+SQL "por concurrencia/tipado/industria". Repaso resumido:

| Argumento | Veredicto |
|---|---|
| "El GIL bloquea concurrencia" | No para I/O. FastAPI/asyncio escala como Node para Phoenix (10k cuadros = ~700 msg/s ≪ límite). |
| "Miles de pings/seg" | Es válido para semáforos con bucles magnéticos. Alumbrado reporta cada 1-15 s. No aplica. |
| "Tipado dinámico → errores" | Mitigado con `mypy/pyright` (tipado estático en CI) y **Pydantic** que valida en runtime — TS sin librerías extra **no** valida en runtime. |
| "Industria usa TS" | **Falso**. Schneider, Siemens y SICE usan C++/Java en el núcleo. Home Assistant es 100% Python. Casi nadie usa Node para el centro EMS. |
| "Python es bueno para ML" | Cierto y conveniente: cuando llegue el motor de predicción de consumo eléctrico, ya está en el mismo runtime. |

**Decisión:** **seguir en Python (FastAPI + SQLAlchemy + Pydantic)**.
Migrar costaría 2-3 semanas y no añadiría valor práctico. Si llegamos a
~50.000 cuadros con telemetría a 1 Hz, antes que TS consideraríamos
Rust o Go para el ingestor MQTT — Node no resuelve mejor que asyncio.
El frontend sigue siendo HTML + vanilla JS; cuando crezca, lo pasaremos
a React/TypeScript dejando el backend en Python (combo estándar en la
industria).

### 5.3 Seed demo con credenciales conocidas
- En modo demo, `admin` se siembra con:
  - contraseña: `phoenix123`
  - PIN: `1234`
  - patrón: `01258` (Z diagonal)
- `/auth/info` revela los 4 valores cuando `PHOENIX_DEMO_MODE=true`,
  para que la pantalla de login los pre-rellene.
- En producción se desactiva con `PHOENIX_DEMO_MODE=false`.

---

## 6. Hardware destino · PLCs / edge AI

### 6.1 Arquitectura de despliegue recomendada — 2026-06
Phoenix-Light no necesita PLC industrial Siemens/Beckhoff salvo que el
cliente lo exija contractualmente. Despliegue real previsto en dos capas:

**Capa A · En cada cuadro físico (campo):**
- **ESP32-S3-WROOM** (~10 €): control de relés + Modbus + telemetría.
- **ESP32-S3 + módulo 4G** (p. ej. LilyGO T-SIM7600, ~50 €): para
  cuadros aislados sin red cableada.
- *Opcional*, si hay analítica local: ESP32-S3 + **Coral USB Edge TPU**
  (4 TOPS, ~60 €) para detección de presencia/ruido con MFCC.

**Capa B · Centro de mando (gateway / pequeño servidor):**
Aquí corre Phoenix-Light entero (FastAPI + SQLite/PostgreSQL + MQTT)
junto con la analítica de IA.

| Hardware | NPU | Coste aprox. | Cuándo elegirlo |
|---|---|---|---|
| **Raspberry Pi 5 + Hailo-8 HAT** | 26 TOPS | 250 € | **Por defecto.** Hasta ~1000 cuadros |
| **NVIDIA Jetson Orin Nano Super 8 GB** | 67 TOPS | 250 € | Si hay computer vision |
| **NVIDIA Jetson Orin NX 16 GB** | 100 TOPS | 600 € | Municipios grandes (>10 000 cuadros) |
| **PLCnext de Phoenix Contact** | Variable | 800-2000 € | Si el cliente exige PLC industrial real |
| **Siemens S7-1500 + TM NPU** | Industrial | >3000 € | Solo si lo exige el contrato |

**Software stack en el gateway:**
- Python 3.11+ con FastAPI + SQLAlchemy + Pydantic (lo que ya tenemos).
- **ONNX Runtime** o **TensorFlow Lite** para inferencia.
- **Hailo SDK** si el gateway es Pi + Hailo-8.
- Drivers: `aiomqtt` (ya en uso), `pymodbus`, OPC-UA si llega.

### 6.2 IA que correrá encima (futuro, no en MVP)
- Predicción de consumo eléctrico (scikit-learn, Pandas).
- Detección de averías por autoencoder (TFLite).
- Dimming inteligente por afluencia (rule-based + opcional ML).
- Computer vision con cámara para iluminación adaptativa (YOLO en Hailo).

### 6.3 Arquitectura del Centro de Mando (CM) — diseño eléctrico
Decidido tras revisar Citilux V3/NXT 4G de Arelsa y los esquemas Phoenix
CM (vista interior + diagramas de potencia/control + unifilar). Phoenix
no será un Citilux clonado: arquitectura **abierta** con PLC + E/S +
Modbus + telemetría propia.

**Disposición física del cuadro (4 zonas, separación obligatoria):**

```
ZONA 1 · POTENCIA 230/400 V AC ──── entrada de red, seccionador 4P,
                                    magnetotérmico general 4P,
                                    diferencial 4P 300 mA,
                                    magnetotérmicos por circuito (QF1-4),
                                    contactores (KM1-4), borneros N + PE
ZONA 2 · MEDIDA ──────────────────── analizador de red Modbus (Socomec
                                    DIRIS A-40 / Siemens PAC3220), TIs
                                    (transformadores de intensidad)
ZONA 3 · CONTROL 24 V DC ─────────── fuente DIN 24 V DC, PLC Phoenix
                                    Contact PLCnext AXC F 2152, módulos
                                    Axioline DI/DO, relés intermedios
                                    (con diodo flyback)
ZONA 4 · COMUNICACIONES ──────────── router 4G industrial (Teltonika
                                    RUT241/RUT956), switch industrial
                                    DIN (Phoenix/Moxa)
```

**Cadena de control de un contactor (la decisión clave):**
- PLC = 24 V DC, contactor = bobina 230 V AC → **no se conecta directo nunca**.
- Entre medias un **relé intermedio 24 V DC** (KA1-KA4):
  ```
  DO Axioline (+24V) → bobina KA (24 V DC, con diodo flyback)
                     → contacto KA conmuta 230 V AC
                     → fusible F (2 A gG típico)
                     → bobina KM (230 V AC, A1/A2)
                     → contactos de potencia KM cierran L1/L2/L3
                     → circuito de alumbrado
  ```
- **Razón:** aislamiento galvánico PLC ↔ potencia, mantenimiento barato
  (un relé KA se cambia en 30 s, un módulo Axioline cuesta cientos €),
  protección anti-ruido de los buses Modbus/Ethernet.

**Confirmación (closed-loop, lo que diferencia un buen CM):**
- Cada KM lleva **contacto auxiliar 13-14 (NO)** → entrada digital del PLC.
- El PLC ejecuta la lógica orden + confirmación + consumo:
  | Orden DO | Aux KM | Consumo (analizador) | Diagnóstico |
  |---|---|---|---|
  | ON | Cerrado | > 0 | Correcto |
  | ON | Abierto | 0 | Contactor no cerró |
  | ON | Cerrado | 0 | Línea/luminarias averiadas |
  | OFF | Cerrado | > 0 | Contactor pegado (crítico) |
  | OFF | Abierto | 0 | Correcto |
- Esta es la base para las alarmas `LAMP_OUT`, `LINE_FAILURE`,
  `CONTACTOR_STUCK`, `CIRCUIT_LOAD_DROP` que el motor del software ya
  reconoce. Lo único que falta es publicarlas desde el firmware del PLC
  vía MQTT (futuro).

**Entradas digitales mínimas que cablear al PLC:**
| Señal | Origen | Alarma resultante |
|---|---|---|
| Puerta abierta | Final de carrera / reed switch | `DOOR_OPEN` |
| Diferencial disparado | Contacto auxiliar del diferencial | `LINE_FAILURE` (subtipo) |
| Magnetotérmico general | Aux del 4P general | `LINE_FAILURE` |
| Magnetotérmico circuito 1-4 | Aux de cada QF | Por circuito |
| Confirmación KM1-4 cerrado | 13-14 del contactor | (lógica feedback) |
| Modo manual/auto | Selector frontal | `MANUAL_OVERRIDE` (futuro) |
| Fallo de fase L1/L2/L3 | Relé de fases / analizador | `LINE_FAILURE` |
| Tamper / intrusión | Sensor adicional | `INTRUSION` |

**Hardware mínimo para una primera maqueta funcional (Phoenix CM-P1):**
- 1× PLC Phoenix Contact PLCnext AXC F 2152
- 1× fuente 24 V DC DIN (5 A, p.ej. Phoenix Quint Power)
- 1× módulo Axioline 16 DI (o 2 × 8 DI)
- 1× módulo Axioline 8 DO
- 4× contactores 4 polos, bobina 230 V AC, con auxiliar 1NO
- 4× relés intermedios 24 V DC con base DIN (+ diodo flyback)
- 1× analizador de red trifásico Modbus RS-485 (DIRIS A-40 o EM340)
- 3× TIs según corriente máxima esperada
- 1× router 4G industrial Teltonika RUT241/RUT956
- 1× switch DIN 5 puertos
- 1× sensor de puerta (reed magnético o final de carrera)
- 1× protector sobretensiones (SPD tipo 2)
- Protecciones: 1 seccionador 4P, 1 magneto 4P general, 1 diferencial 4P
  300 mA, 4 magnetos 2P por circuito, fusibles para bobinas de KMs

**Por qué Phoenix Contact PLCnext y no WAGO PFC200:**
- Coherencia de nombre con el proyecto Phoenix.
- Linux abierto, IEC 61131-3, soporta MQTT y Modbus TCP/RTU.
- Módulos Axioline son robustos y modulares.
- WAGO es perfectamente válido como alternativa de coste si hace falta.

**Lo que NO entra en la Fase 1 (queda para fases 2/3):**
- Detección luminaria-a-luminaria → necesita DALI, nodos LoRa/NB-IoT o
  PLC por línea (PLC narrowband sobre el propio cableado). En Fase 1
  solo detectamos anomalías a nivel de circuito (consumo esperado vs
  real).

### 6.4 Por qué NO usamos Citilux (Arelsa V3 / NXT 4G)
Lo evaluamos durante el diseño y queda como referencia cerrada de la
que nos diferenciamos a propósito:

- **Equipo propietario**, sin pantalla local. Toda la gestión va por su
  software CITIGIS (también propietario) → licencias y dependencia.
- Alimentación 12 V DC (bornes 36 +, 35 −) o 230 V AC para medida.
- Acceso solo por Ethernet con configuración por instalador Arelsa.
- Funcionalidades aceptables (mando, analizador, alarmas, datalogger)
  pero el ecosistema es cerrado: no puedes meter tu propio software
  central sin pagar integración o licenciar CITIGIS.
- **Razón para Phoenix:** queremos exactamente lo que ofrece Citilux,
  pero con stack abierto (Phoenix Contact PLCnext + Python/FastAPI).
  Mismo control, sin licencias, sin proveedor único, sin firmware
  cerrado, con la posibilidad de añadir IA y módulos propios sin pagar
  a nadie.

Citilux nos sirve como **catálogo de funciones a igualar o superar**:
mando, medición, alarmas físicas, comunicaciones 4G, eventos.

### 6.5 Plan por fases del despliegue hardware
Refinamos las fases para distinguir mejor el "control por cuadro" del
"control por luminaria" (cada uno necesita hardware muy distinto):

| Fase | Alcance hardware | Alcance software | Estado |
|---|---|---|---|
| **F1** | PLC + Axioline DI/DO + contactores con auxiliar + analizador Modbus + router 4G | Control por cuadro: encender/apagar circuitos, alarmas físicas (puerta, fases, magnetos, diferencial), telemetría a la plataforma | El software ya está; falta el firmware del PLC publicando MQTT |
| **F2** | Mismo F1 + histórico de consumos | Detección de **consumo anómalo por circuito** (esperado vs real), alarmas automáticas, calendario y planificación de mantenimiento | El motor ya tiene los hooks; falta `expected_power_w` y las 3 alarmas (LOAD_DROP, OVERLOAD, CONTACTOR_STUCK) |
| **F3** | Nodos por luminaria: DALI (instalación nueva), LoRa/NB-IoT (retrofit inalámbrico) o PLC narrowband sobre cableado | Detección **luminaria-a-luminaria**: "farola 17 averiada", dimming individual, mapa de drivers | Diseño pendiente |
| **F4** | Sin hardware extra | IA predictiva: detectar luminarias **degradadas antes** del fallo total, predicción de consumo, optimización tarifaria | Diseño pendiente |

### 6.6 Lógica de detección "consumo esperado vs real" (Fase 2)
La pieza estrella del software de alumbrado público. Se basa en
comparar la medida del analizador contra la potencia nominal del
circuito y el estado ordenado por el PLC:

| Estado ordenado | Aux contactor | Consumo medido | Diagnóstico |
|---|---|---|---|
| ON (relay=on, dim>0) | Cerrado | ≈ esperado (±20 %) | ✅ Correcto |
| ON | Cerrado | < 50 % del esperado | ⚠ `CIRCUIT_LOAD_DROP` — luminarias fundidas |
| ON | Cerrado | > 130 % del esperado | 🔴 `CIRCUIT_OVERLOAD` — fuga, derivación, cortocircuito |
| ON | Cerrado | 0 | 🔴 `LAMP_OUT` (ya implementado) |
| ON | **Abierto** | 0 | 🔴 `CONTACTOR_FAIL_TO_CLOSE` — contactor no cerró |
| OFF (relay=off) | **Cerrado** | > 0 | 🔴 `CONTACTOR_STUCK` — contactor pegado, no abre |
| OFF | Abierto | 0 | ✅ Correcto |

**Cómo se obtiene el valor esperado:**
- A nivel circuito: suma de `power_w` de sus luminarias × factor de
  dimming actual.
- Permite tolerancias por circuito (algunos LED tienen drift térmico
  +/- 5 %).
- En despliegues mixtos (vapor sodio + LED), el cálculo es por
  luminaria.

**Por qué el `expected_power_w` es campo del Circuit y no del Cabinet:**
- Un cuadro puede tener 4 circuitos con 10, 14, 8 y 12 luminarias.
- Cada circuito tiene su nominal propio.
- El diagnóstico es por circuito porque ahí está el contactor y el
  magnetotérmico (la unidad de detección).

### 6.7 Aviso legal — instalación de baja tensión
Trabajos eléctricos a 230/400 V requieren empresa o personal con
**habilitación de instalador de baja tensión**, regulada en España
por la ITC-BT-03 del REBT. El software Phoenix-Light no sustituye
esta habilitación: ofrece la capa de telegestión/diagnóstico, pero el
cuadro físico debe ser instalado y certificado por un profesional
autorizado.
