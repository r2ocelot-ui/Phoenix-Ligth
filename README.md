# Phoenix-Light

Prototipo de software de **telegestión y eficiencia energética para cuadros de alumbrado público exterior** (concepto tipo Citilux / ETRA / SICE).

El sistema permite supervisar, controlar y optimizar el funcionamiento de cuadros eléctricos de alumbrado a través de un backend ligero, una capa de comunicación M2M (MQTT/HTTP) y firmware embebido en el cuadro.

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
│   ├── main.py                  # Bootstrap FastAPI + MQTT lifecycle
│   ├── core/
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   └── mqtt_client.py       # Wrapper asyncio del cliente MQTT
│   ├── api/v1/
│   │   ├── cabinets.py          # CRUD de cuadros
│   │   ├── measurements.py      # Consulta histórica
│   │   ├── alarms.py            # Listado / ACK de alarmas
│   │   └── control.py           # ON/OFF/Dimming
│   ├── schemas/
│   │   ├── measurement.py       # Modelos Pydantic
│   │   └── alarm.py
│   └── services/
│       ├── ingest.py            # Procesa telemetría entrante
│       ├── alarm_engine.py      # Reglas de detección de fallos
│       └── dimming_controller.py# Perfiles horarios + sensores lux
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

```bash
docker compose up -d           # Mosquitto + TimescaleDB + Backend
python simulator/cabinet_simulator.py --cabinet-id CAB-001
```

Endpoints útiles:
- `http://localhost:8000/docs` — Swagger / OpenAPI para integradores
- `http://localhost:8000/api/v1/cabinets/CAB-001/alarms` — alarmas activas
