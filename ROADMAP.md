# Phoenix-Light — Roadmap

> **Notación**
> - `V` = **Versión** (hito funcional, cambio de capacidades visible para el usuario).
> - `R` = **Revisión** (reparación, modificación o nueva feature dentro de una versión).
> - Estado: `[x]` hecho · `[~]` en curso · `[ ]` pendiente.

---

## V0 — Prototipo MVP ✅
Demostrar el bucle completo: edge → MQTT → backend → alarma → API.

| Rev | Tipo | Descripción | Estado |
|---|---|---|---|
| R0.1 | feat | Esqueleto FastAPI + MQTT (`aiomqtt`) + cliente ESP32 (PZEM-004T) | [x] |
| R0.2 | feat | Motor de alarmas: `LAMP_OUT`, `LINE_FAILURE`, `OVERVOLTAGE`, `UNDERVOLTAGE` | [x] |
| R0.3 | feat | Perfiles horarios de dimming + control REST de relé y dim | [x] |
| R0.4 | feat | Simulador de cuadro y demo standalone sin broker | [x] |
| R0.5 | docs | README con arquitectura, contrato MQTT y guía de hardware | [x] |
| R0.6 | fix | `timestamp` opcional con default en servidor (firmware enviaba `""`) | [x] |
| R0.7 | fix | Sin falso `LAMP_OUT` cuando el circuito está comandado OFF | [x] |
| R0.8 | fix | Alarmas con estado (raise-once / clear-on-resolve) | [x] |
| R0.9 | feat | Scheduler de dimming conectado al bus MQTT | [x] |
| R0.10 | test | `pytest` para motor de alarmas y perfiles de dimming | [x] |
| R0.11 | fix | `acknowledge_all` idempotente (sin 404 espurio) | [x] |
| R0.12 | feat | CORS abierto por defecto (configurable) para dashboards de integrador | [x] |
| R0.13 | feat | `COMMUNICATION_LOSS` vía suscripción al topic `status` (LWT) | [x] |
| R0.14 | feat | `ambient_lux` opcional en telemetría → realimentado al scheduler | [x] |
| R0.15 | ci | GitHub Actions: `pytest` en cada push / PR | [x] |

---

## V0.1 — Hardening (siguiente paso) 🔧
Tapar los huecos que aún quedan antes de pensar en producción.

| Rev | Tipo | Descripción | Estado |
|---|---|---|---|
| R0.1.1 | fix | Validación de coherencia: `P ≈ V·I·cos φ` (descartar telemetría incongruente) | [ ] |
| R0.1.2 | feat | API Key por integrador (header `X-API-Key`) — gate mínimo de auth | [ ] |
| R0.1.3 | feat | Suscripción a `cabinets/+/status` con timeout heartbeat (no solo LWT) | [ ] |
| R0.1.4 | feat | Persistencia ligera con SQLite (estado de cuadros + cola de alarmas) | [ ] |
| R0.1.5 | test | Cobertura del control API (`/relay`, `/dim`) y endpoint de alarmas | [ ] |
| R0.1.6 | fix | Healthcheck en `docker-compose` para que el backend espere a Mosquitto | [ ] |
| R0.1.7 | docs | `.env.example` con todas las variables `PHOENIX_*` | [ ] |
| R0.1.8 | chore | Logging estructurado (JSON) para integración con ELK/Loki | [ ] |

---

## V1.0 — Listo para piloto urbano 🏙️
Despliegue real en 5-10 cuadros con un cliente.

| Rev | Tipo | Descripción | Estado |
|---|---|---|---|
| R1.0.1 | feat | TimescaleDB para series temporales (V/I/P/cos φ por minuto) | [ ] |
| R1.0.2 | feat | Zona horaria por cuadro (`tz` en metadatos) → scheduler la respeta | [ ] |
| R1.0.3 | feat | MQTT con TLS + ACL por cuadro (cada ESP32 con su credencial) | [ ] |
| R1.0.4 | feat | WebSocket `/ws/alarms` para streaming en tiempo real a integradores | [ ] |
| R1.0.5 | feat | Rate limiting (`slowapi`) en endpoints de control | [ ] |
| R1.0.6 | feat | Roles + JWT (admin / operador / integrador read-only) | [ ] |
| R1.0.7 | feat | Driver Modbus RTU para SDM630 / CIRCUTOR CVM-C10 (analizador certificable) | [ ] |
| R1.0.8 | feat | Store-and-forward en el ESP32 (LittleFS) para no perder telemetría offline | [ ] |
| R1.0.9 | feat | OTA del firmware vía `ArduinoOTA` o cliente HTTPS contra el backend | [ ] |
| R1.0.10 | feat | Endpoint Prometheus `/metrics` + dashboards Grafana de muestra | [ ] |

---

## V1.1 — Edge maduro 📡
Variantes de hardware/comms para despliegues reales sin Wi-Fi.

| Rev | Tipo | Descripción | Estado |
|---|---|---|---|
| R1.1.1 | feat | Firmware ESP32-S3 + SIM7080G para NB-IoT / LTE-M | [ ] |
| R1.1.2 | feat | Variante Raspberry Pi CM4 con Docker en el edge (cuadros grandes) | [ ] |
| R1.1.3 | feat | Cliente LoRaWAN (Class A, payload CBOR comprimido) | [ ] |
| R1.1.4 | feat | Edge analytics: detección local de armónicos y picos | [ ] |
| R1.1.5 | fix | Reconexión MQTT con backoff exponencial + límite de retries | [ ] |

---

## V2.0 — Integración Smart City 🌆
Conectar con plataformas tipo ETRA, SICE, Telefónica Smart Cities.

| Rev | Tipo | Descripción | Estado |
|---|---|---|---|
| R2.0.1 | feat | Dashboard React + Vite (mapa Leaflet + estado de cuadros) | [ ] |
| R2.0.2 | feat | Adaptador FIWARE / NGSI-LD (`StreetlightControlCabinet`) | [ ] |
| R2.0.3 | feat | OAuth 2.0 client-credentials por integrador | [ ] |
| R2.0.4 | feat | Modelo multi-tenant (organización → instalación → cuadro) | [ ] |
| R2.0.5 | feat | Webhook saliente para alarmas críticas (Slack / Teams / SMS) | [ ] |
| R2.0.6 | feat | Exportación CSV / Parquet de telemetría para auditorías | [ ] |
| R2.0.7 | feat | Versionado de API (`/api/v2/...`) sin romper integradores | [ ] |

---

## V2.1 — Eficiencia energética y analítica 📊
Donde está el valor real para el cliente (ahorro €€€).

| Rev | Tipo | Descripción | Estado |
|---|---|---|---|
| R2.1.1 | feat | Agregación kWh por cuadro / circuito / mes + reporte PDF | [ ] |
| R2.1.2 | feat | Dimming adaptativo según sensor de tráfico o presencia (LoRaWAN) | [ ] |
| R2.1.3 | feat | Mantenimiento predictivo: tiempo a fallo por degradación de cos φ | [ ] |
| R2.1.4 | feat | Optimizador de perfil horario por consumo histórico (mínimo lumínico) | [ ] |
| R2.1.5 | feat | Comparativa con factura del DSO (curva 15-min EDS / SIPS) | [ ] |

---

## V3.0 — Plataforma 🚀
Cuando deje de ser “un prototipo” y empiece a ser “producto”.

| Rev | Tipo | Descripción | Estado |
|---|---|---|---|
| R3.0.1 | feat | Despliegue Kubernetes (Helm chart + HPA) | [ ] |
| R3.0.2 | feat | Aislamiento por tenant en Mosquitto (ACL dinámico) | [ ] |
| R3.0.3 | feat | Marketplace de drivers (PRIME/G3, Zigbee, KNX) | [ ] |
| R3.0.4 | feat | SDK Python / TypeScript para integradores | [ ] |
| R3.0.5 | feat | Auditoría inmutable (append-only) de comandos a cuadros | [ ] |

---

## Convención para nuevas entradas

- Una revisión = una unidad atómica de cambio (un PR, idealmente).
- Tipos: `feat` (nueva capacidad) · `fix` (corrección) · `refactor` · `docs` · `test` · `ci` · `chore`.
- Si un hallazgo nuevo aparece tras una revisión, se añade a la versión actual si es bug,
  o a la siguiente versión si es scope nuevo.
