# Phoenix-Light

Prototipo de software de **telegestión y eficiencia energética para cuadros de alumbrado público exterior** (concepto tipo Citilux / ETRA / SICE).

El sistema permite supervisar, controlar y optimizar el funcionamiento de cuadros eléctricos de alumbrado a través de un backend ligero, una capa de comunicación M2M (MQTT/HTTP) y firmware embebido en el cuadro.

Plan de versiones y revisiones en [`ROADMAP.md`](./ROADMAP.md).

---

## A) Arquitectura de Software

### Stack recomendado

| Capa | Tecnología | Por qué |
|---|---|---|
| Backend / API | **Python 3.11 + FastAPI** | Async nativo, OpenAPI auto-generado, ideal para integradores |
| Broker M2M | **Mosquitto** (MQTT 3.1.1/5.0) | Estándar de facto IoT, QoS, retained messages |
| Time-series DB | **TimescaleDB** (PostgreSQL ext.) | SQL estándar + compresión + downsampling |
| Cache / Pub-Sub interno | **Redis** | Estado en tiempo real de cuadros |
| Frontend | **React + Vite + TailwindCSS** | Dashboards de Smart City |
| Edge firmware | **ESP-IDF / Arduino-ESP32 (C++)** | Soporte nativo MQTT, Modbus, deep-sleep |
| Orquestación | **Docker Compose** (prototipo) → K8s (prod) | Reproducible y portable |

### Diagrama lógico

```
 ┌───────────────────┐      ┌──────────────────┐      ┌─────────────────────┐
 │  Cuadro físico    │      │   Mosquitto      │      │  Backend FastAPI    │
 │  ESP32 + PZEM /   │ MQTT │   (Broker)       │ MQTT │  - Ingest service   │
 │  Modbus analyzer  │─────▶│  TLS + ACL       │─────▶│  - Alarm engine     │
 │  Relé + 0-10V dim │◀─────│                  │◀─────│  - Control API      │
 └───────────────────┘      └──────────────────┘      └──────────┬──────────┘
        ▲                                                        │
        │ LoRaWAN / NB-IoT / Wi-Fi                               ▼
        │                                              ┌─────────────────────┐
        │                                              │  TimescaleDB        │
        │                                              │  + Redis            │
        │                                              └──────────┬──────────┘
        │                                                         │
        │                                              ┌──────────▼──────────┐
        │                                              │  Open REST API      │
        └──────────────────────────────────────────────│  (ETRA / SICE)      │
                                                       └─────────────────────┘
```

### Estructura del backend

```
backend/
├── app/
│   ├── main.py                  # Bootstrap FastAPI + MQTT lifecycle + init_db
│   ├── core/
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── database.py          # Engine/sesión SQLAlchemy + init_db
│   │   ├── security.py          # Hash PBKDF2 + JWT HS256 (stdlib)
│   │   └── mqtt_client.py       # Bus MQTT asíncrono (telemetría/comandos/alarmas)
│   ├── api/v1/
│   │   ├── auth.py              # register / login / me
│   │   ├── users.py             # gestión de usuarios, rangos y permisos
│   │   ├── audit.py             # historial append-only
│   │   ├── alarms.py            # alarmas activas (protegido por permiso)
│   │   └── control.py           # ON/OFF/Dimming (protegido por permiso)
│   ├── models/                  # ORM: User, AuditLog
│   ├── schemas/                 # Pydantic: measurement, alarm, user, audit
│   └── services/
│       ├── alarm_engine.py      # Reglas de detección de fallos
│       ├── dimming_controller.py# Perfiles horarios + sensores lux
│       ├── ranks.py             # Rangos, permisos y progresión
│       ├── auth.py              # Deps: current_user / require_permission
│       └── audit_log.py         # Registro append-only
└── requirements.txt
```

### Tópicos MQTT (contrato)

| Dirección | Tópico | Payload |
|---|---|---|
| Edge → Cloud | `phoenix/cabinets/{cabinet_id}/telemetry` | JSON: voltaje, corriente, P, cosφ |
| Edge → Cloud | `phoenix/cabinets/{cabinet_id}/status` | JSON: online/offline (LWT) |
| Cloud → Edge | `phoenix/cabinets/{cabinet_id}/cmd/relay` | `{"state": "on"\|"off"}` |
| Cloud → Edge | `phoenix/cabinets/{cabinet_id}/cmd/dim` | `{"level": 0-100}` |
| Cloud → Cloud | `phoenix/alarms` | JSON: tipo, severidad, cabinet_id |

---

## B) Requerimientos de Hardware

### Microcontrolador del cuadro

| Opción | Cuándo | Ventajas |
|---|---|---|
| **ESP32-WROOM-32** | Cuadros con Wi-Fi/Ethernet cercana | Bajo coste (~3 €), MQTT/Modbus nativo, OTA |
| **ESP32-S3 + SIM7080G** | Despliegues urbanos sin Wi-Fi | NB-IoT/CAT-M1 integrado, bajo consumo |
| **Raspberry Pi CM4** | Cuadros grandes con varios circuitos | Linux completo, Docker en el edge, Modbus RTU + TCP |

**Recomendación**: empezar con **ESP32-WROOM-32** para PoC y escalar a CM4 cuando se necesite procesamiento local (edge analytics).

### Sensores de medición eléctrica

| Sensor | Interfaz | Precisión | Uso |
|---|---|---|---|
| **PZEM-004T v3** | UART | Clase 1 | Prototipo, monofásico |
| **SDM630-Modbus** | RS-485 Modbus RTU | Clase 0.5 | Trifásico, instalación DIN |
| **CIRCUTOR CVM-C10** | RS-485 / Ethernet Modbus | Clase 0.5S | Producción, certificado MID |
| **Pinza Rogowski + LTC2440** | Analógica → ADC | Variable | Retrofit no invasivo |

Para certificación (MID) en alumbrado público se recomienda **CVM-C10** o **SDM630-MID** sobre **Modbus RTU** (RS-485).

### Tecnologías de comunicación

| Tech | Alcance | Consumo | Cuándo |
|---|---|---|---|
| **Wi-Fi** | Local | Alto | Pruebas en banco, edificios |
| **LoRaWAN** | 2-15 km | Muy bajo | Zonas rurales, baja cadencia (cada 15 min) |
| **NB-IoT / LTE-M** | Cobertura celular | Bajo | Urbano, telegestión real, latencia <10 s |
| **PLC (PRIME/G3)** | Sobre la red eléctrica | — | Despliegues con DSO (Iberdrola, EDP) |

**Recomendación**: **NB-IoT** para producción urbana (sin desplegar gateways propios) y **LoRaWAN** si se controla la red. Wi-Fi solo para PoC.

---

## Quick start (PoC)

### Opción A — solo el panel web, con datos de demo (sin broker)
```bash
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload
# Abre http://localhost:8000/ui/
```
En modo demo (`PHOENIX_DEMO_MODE=true`, por defecto) el backend inyecta
telemetría sintética de 4 cuadros, así que el panel cobra vida al instante.

### Opción B — pila completa (broker MQTT + simulador real)
```bash
docker compose up -d
python simulator/cabinet_simulator.py --cabinet-id CAB-001
```

> El **primer usuario** que registres en el panel será `owner`.

Endpoints útiles:
- `http://localhost:8000/ui/` — **Panel web Phoenix Light**
- `http://localhost:8000/docs` — Swagger / OpenAPI para integradores
- `http://localhost:8000/api/v1/cabinets` — snapshot en vivo de los cuadros (requiere token)

## Panel web (Phoenix Light UI)

SPA en un único archivo (`frontend/index.html`, sin build) servida por el propio
backend en `/ui/`. Misma familia visual que el resto de divisiones de Kumiho
(base oscura slate, tipografía Inter + monoespacio) con **acento rojo/fuego** de
Phoenix. Secciones:

- **Inicio** — KPIs de la red (cuadros, online, alarmas, potencia total) e incidencias.
- **Cuadros** — tarjetas con telemetría en vivo (V/I/P/cos φ) y nivel de dimming.
- **Control** — encendido/apagado y regulación por cuadro (requiere `cabinet:control`).
- **Alarmas** — incidencias activas y ACK (requiere `alarm:ack`).
- **Usuarios** — gestión de cuentas y rangos (requiere `user:view`/`user:manage`).
- **Auditoría** — historial de acciones (requiere `audit:read`).

La navegación se filtra automáticamente según los permisos del usuario. El tema
se controla con variables CSS (`--accent*`): cambiar ese bloque reskinea el panel
para otra división (p. ej. morado para Hydra, azul para Argus).

## Usuarios, rangos y auditoría

La API requiere autenticación (JWT). Los endpoints están protegidos por **permisos**,
que se derivan del **rango** del usuario más sus overrides individuales.

| Rango | Nivel | Permisos por defecto |
|---|---|---|
| `novato` | 0 | leer cuadros |
| `operador` | 1 | + control (encendido/apagado/dimming) |
| `tecnico` | 2 | + ACK de alarmas, gestión de cuadros |
| `supervisor` | 3 | + ver auditoría, ver usuarios |
| `admin` | 4 | + gestionar usuarios y rangos |
| `owner` | 5 | todo (`*`) |

- **Progresión**: los usuarios acumulan `activity_points` al operar. Al alcanzar el umbral
  de puntos + antigüedad quedan *elegibles* para el siguiente rango (ver `/auth/me`). El
  ascenso lo confirma un admin (`POST /users/{id}/promote`), o automático si se activa
  `PHOENIX_AUTO_PROMOTE_ENABLED` (con tope `PHOENIX_AUTO_PROMOTE_MAX_RANK`).
- **Overrides por usuario**: `extra_permissions` y `denied_permissions` ajustan permisos
  por encima/por debajo del rango (`POST /users/{id}/permissions`).
- **Bootstrap**: el **primer usuario registrado** es `owner`; el resto nacen `novato`.
- **Historial**: cada acción relevante (login, control, cambios de rango) queda en un
  log append-only consultable en `GET /api/v1/audit`.

```bash
# 1) Registrar (el primero es owner) y obtener token
curl -X POST localhost:8000/api/v1/auth/register \
     -H 'Content-Type: application/json' \
     -d '{"username":"admin","password":"secret123"}'
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
     -d 'username=admin&password=secret123' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# 2) Llamar a un endpoint protegido
curl -X POST localhost:8000/api/v1/cabinets/CAB-001/dim \
     -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"level":50}'
```

## Tests

```bash
cd backend && pytest        # alarmas, dimming, rangos/permisos y API de auth
python simulator/standalone_alarm_demo.py   # demo de lámpara fundida sin broker
```

## Notas de diseño

- **Alarmas con estado:** cada alarma se levanta una sola vez al cruzar el umbral
  y se limpia (evento `cleared`) al resolverse. No se reemiten en cada muestra,
  así que la lista de alarmas activas está acotada (una entrada por tipo y cuadro).
- **Dimming automático:** un scheduler resuelve el perfil horario cada
  `PHOENIX_DIMMING_INTERVAL_S` segundos y publica `cmd/dim` a cada cuadro conocido.
  El estado comandado (relé + nivel) se registra para que el motor de alarmas
  distingua un apagado intencionado de una lámpara fundida (no hay falso `LAMP_OUT`
  cuando el dimming está a 0).
- **Timestamp:** el `timestamp` de la telemetría es opcional; si el edge no lo
  envía, el backend sella la hora de recepción.
