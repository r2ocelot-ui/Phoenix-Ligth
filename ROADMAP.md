# Phoenix Light — Roadmap

> **Cómo leer este documento**
> - `V0` = **Fundación**: lo ya entregado y estable. Es la base sobre la que se construye.
> - `V1, V2…` = **Hitos temáticos** del producto. Cada uno tiene un tema claro
>   ("lo visual", "operación avanzada", "histórico", "edge real"…) y agrupa
>   las features que lo llevan al estado "completo y sin fallos".
> - Dentro de cada hito, las **R** son revisiones atómicas (un PR cada una).
> - Estado: `[x]` hecho · `[~]` en curso · `[ ]` pendiente.
> - **Snapshots**: cada hito que se cierra recibe un tag git
>   (`v0-fundacion`, `v1-visual`…) — es la "foto" estable a la que poder volver.

---

## V0 — Fundación ✅
Lo entregado hasta hoy: el esqueleto funcional de Phoenix Light.

- Backend FastAPI + cliente MQTT asíncrono, motor de alarmas (lámpara
  fundida, fallo de línea, sobre/subtensión, comunicación), perfiles de
  dimming, simulador y firmware ESP32 de referencia.
- Identidad: registro/login JWT, rangos con permisos
  (`novato → operador → técnico → supervisor → admin → owner`), overrides
  por usuario, progresión con puntos, historial append-only.
- Persistencia SQLite (usuarios, auditoría, registro de cuadros, circuitos,
  farolas).
- Panel web propio (`/ui/`) con login, KPIs, tarjetas de cuadros, control,
  alarmas, gestión de usuarios y auditoría. WebSocket en vivo + fallback.
- Mapa Leaflet con CM y farolas numeradas, coloreables por estado, CM,
  circuito o fase, con leyenda.
- Lanzadores `start.bat` / `start.sh` con usuario demo (`admin`/`phoenix123`).

**Snapshot:** `v0-fundacion` (al cerrar). Etapas internas: `v0-mvp`,
`v0.2-identity`, `v0.3-panel`, `v0.4-map-realtime`, `v0.5-topology`.

---

## V1 — Forma visual / Experiencia Phoenix 🎨
Que el panel **se sienta Phoenix**, no un reskin de Hydra. Identidad propia,
pulido fino y experiencia de uso a la altura del producto.

| Rev | Tipo | Descripción |
|---|---|---|
| R1.1 | feat | Pantalla de carga con emblema Phoenix animado (llama "respirando") |
| R1.2 | feat | Tipografía y jerarquía revisadas (display + cuerpo + monospace) |
| R1.3 | feat | Iconografía SVG propia (farola, cuadro, circuito, fase) |
| R1.4 | feat | Capa de mapa diferenciada: iconos de farola en vez de círculos, halo de calor por consumo, clústeres a poco zoom |
| R1.5 | feat | Estilo de tiles propio (oscuro con tinte ámbar muy sutil) |
| R1.6 | feat | Animaciones de transición entre vistas (sin abuso) |
| R1.7 | feat | Modo claro/oscuro y respeto a `prefers-color-scheme` |
| R1.8 | feat | Sistema de diseño documentado (`docs/design-system.md`) y *tokens* CSS reutilizables por otras divisiones |
| R1.9 | feat | Página "Acerca de" con identidad Kumiho + Phoenix |
| R1.10 | a11y | Accesibilidad: contraste AA, foco visible, navegación por teclado, lector de pantalla |
| R1.11 | feat | Responsive serio (tablet de operación + móvil de consulta) |
| R1.12 | i18n | Internacionalización (es / en) con archivos de cadenas |

**Cierre:** snapshot `v1-visual`.

---

## V2 — Operación avanzada 🎛️
Pasar de "encender / apagar / dimmear" a **operar la red como un EMS de verdad**.

| Rev | Tipo | Descripción |
|---|---|---|
| R2.1 | feat | Calendario de programaciones (encendidos/apagados por día y rango) |
| R2.2 | feat | Astro-reloj: cálculo solar por coordenadas (orto/ocaso) |
| R2.3 | feat | Festivos y excepciones (fechas especiales, eventos) |
| R2.4 | feat | "Escenas" guardadas (ej. *modo carnaval*, *modo noche-cerrada*) |
| R2.5 | feat | Perfiles de dimming por tramos (00–06, 06–08, …) editables visualmente |
| R2.6 | feat | Control granular: por CM → circuito → farola (cuando el HW lo permita) |
| R2.7 | feat | Mando manual con caducidad ("dejar fijo 80% hasta las 02:00") |
| R2.8 | feat | Modo emergencia (todo al 100%) y modo ahorro (mínimo legal) con un clic |
| R2.9 | feat | Alta/edición de CM, circuitos y farolas desde la UI (hoy solo API) |
| R2.10 | feat | Importación masiva de farolas (CSV / GeoJSON / shapefile) |
| R2.11 | feat | Doble confirmación + razón obligatoria para acciones críticas |

**Cierre:** snapshot `v2-operacion`.

---

## V3 — Datos, histórico y analítica 📊
Phoenix deja de ser "snapshot en vivo" y se vuelve **memoria + inteligencia
sobre la red**.

| Rev | Tipo | Descripción |
|---|---|---|
| R3.1 | feat | Persistir telemetría en serie temporal (SQLite → TimescaleDB cuando crezca) |
| R3.2 | feat | Persistir alarmas con ciclo de vida (abierta, reconocida, resuelta) |
| R3.3 | feat | Gráficas en cada cuadro: V/I/P/cos φ por hora/día/semana |
| R3.4 | feat | kWh por CM, por circuito, por zona, por mes |
| R3.5 | feat | Comparativa interanual y vs. objetivo de ahorro |
| R3.6 | feat | Ratio de horas encendido vs. astro-reloj (detecta cuadros mal programados) |
| R3.7 | feat | Informes PDF mensuales por instalación (consumo, alarmas, disponibilidad) |
| R3.8 | feat | Exportación CSV / Parquet para auditorías |
| R3.9 | feat | Mapa de calor histórico de averías (zonas problemáticas) |
| R3.10 | feat | Disponibilidad (% uptime) por cuadro y SLA por integrador |

**Cierre:** snapshot `v3-datos`.

---

## V4 — Inteligencia y mantenimiento 🧠
De **reactivo** ("la farola está fundida") a **predictivo** ("esa lámpara
fallará en 2 semanas, planifica el cambio").

| Rev | Tipo | Descripción |
|---|---|---|
| R4.1 | feat | Detección de degradación de cos φ → predicción de fin de vida de lámpara |
| R4.2 | feat | Detección de derivas (subida lenta de consumo → posible cortocircuito) |
| R4.3 | feat | Análisis de armónicos (cuando el analizador lo soporte) |
| R4.4 | feat | Órdenes de trabajo: alarmas → tickets asignables a técnicos |
| R4.5 | feat | Mantenimiento preventivo programado (limpieza, revisión, retiro) |
| R4.6 | feat | Histórico por farola: cuándo se instaló, cuándo se cambió la lámpara |
| R4.7 | feat | Optimización automática del perfil de dimming según consumo histórico |
| R4.8 | feat | Detección de farolas "huérfanas" (encendidas sin estar en programación) |
| R4.9 | feat | Sugerencias de eficiencia ("baja CM-003 al 60% entre 02–05") |
| R4.10 | feat | Webhook saliente de alarmas críticas (Slack/Teams/SMS/Telegram) |

**Cierre:** snapshot `v4-inteligencia`.

---

## V5 — Edge real / Hardware 📡
Pasar del simulador a **cuadros reales en la calle**. Esta versión depende
de hardware físico y se valida sobre el terreno.

| Rev | Tipo | Descripción |
|---|---|---|
| R5.1 | feat | Firmware ESP32 maduro: store-and-forward (no perder datos sin red) |
| R5.2 | feat | OTA: actualizar firmware remotamente desde el panel |
| R5.3 | feat | Driver Modbus RTU real (SDM630-MID, CIRCUTOR CVM-C10) |
| R5.4 | feat | Variante NB-IoT/LTE-M (ESP32-S3 + SIM7080G) para zonas sin Wi-Fi |
| R5.5 | feat | Variante LoRaWAN (zonas con gateway propio) |
| R5.6 | feat | Variante Raspberry Pi CM4 para cuadros grandes con edge analytics |
| R5.7 | feat | Nodos individuales por farola (Zhaga D4i / DALI-2) para control por punto |
| R5.8 | feat | MQTT con TLS + ACL por cuadro (cada equipo con su credencial) |
| R5.9 | feat | Reloj NTP en el edge + sincronización de tiempo |
| R5.10 | feat | Healthcheck de hardware en la UI (firmware, batería, RSSI, uptime) |

**Cierre:** snapshot `v5-edge`.

---

## V6 — Smart City / Integración Kumiho 🏙️
Phoenix deja de ser una isla y se conecta al **resto del ecosistema Kumiho**
(Hydra, Argus, Osiris…) y a plataformas de Smart City externas.

| Rev | Tipo | Descripción |
|---|---|---|
| R6.1 | feat | API pública versionada con OpenAPI y guía para integradores |
| R6.2 | feat | OAuth 2.0 / API keys por integrador con cuota y rate limit |
| R6.3 | feat | Adaptador FIWARE / NGSI-LD (`StreetlightControlCabinet`, `Streetlight`) |
| R6.4 | feat | Webhooks y suscripciones por evento |
| R6.5 | feat | Integración con Hydra: ajustar dimming según tráfico real |
| R6.6 | feat | Integración con Argus: subir luz cuando hay incidencia en cámara |
| R6.7 | feat | Integración con Osiris (residuos) y Cernunnos (medio ambiente) |
| R6.8 | feat | SSO unificado Kumiho (un login para todas las divisiones) |
| R6.9 | feat | Tema unificado Kumiho Group (cabecera común entre apps) |
| R6.10 | feat | Conectores con plataformas externas tipo ETRA / SICE / Telefónica |

**Cierre:** snapshot `v6-smartcity`.

---

## V7 — Producción y escala 🚀
"Sin fallos" de verdad: lo que hace falta para vender Phoenix a un
**ayuntamiento real** y dormir tranquilo.

| Rev | Tipo | Descripción |
|---|---|---|
| R7.1 | feat | Multi-tenant: organización → instalación → cuadros, datos aislados |
| R7.2 | feat | Despliegue Kubernetes (Helm chart + HPA) y PostgreSQL/TimescaleDB |
| R7.3 | feat | Alta disponibilidad: réplicas, balanceo, failover del broker |
| R7.4 | feat | Backups automáticos + restore probado |
| R7.5 | feat | Logging estructurado JSON + tracing OpenTelemetry |
| R7.6 | feat | Métricas Prometheus + dashboards Grafana de referencia |
| R7.7 | sec | Refresh tokens, rotación, revocación, 2FA opcional |
| R7.8 | sec | Auditoría de seguridad y pentest (OWASP top 10) |
| R7.9 | sec | Cifrado en tránsito (TLS everywhere) y en reposo |
| R7.10 | docs | Manual de instalación, manual de usuario por rol, runbooks de incidencias |
| R7.11 | feat | Soporte técnico: panel de salud por instalación, alertas a operaciones |

**Cierre:** snapshot `v7-produccion`.

---

## V8 — Móvil y campo 📱
El técnico que está **en la calle** con el casco y la escalera también es
usuario de Phoenix. Esta versión es para él.

| Rev | Tipo | Descripción |
|---|---|---|
| R8.1 | feat | PWA instalable (funciona sin conexión, sincroniza al recuperarla) |
| R8.2 | feat | Escaneo de QR/NFC en farola → su ficha completa en 1 segundo |
| R8.3 | feat | Partes de avería desde móvil: foto + ubicación + voz a texto |
| R8.4 | feat | Mapa offline con caché de tiles para zonas habituales |
| R8.5 | feat | Ruta optimizada de mantenimiento del día |
| R8.6 | feat | Confirmación de trabajo con foto antes/después |
| R8.7 | feat | App nativa (Capacitor / Tauri) si el cliente la pide |

**Cierre:** snapshot `v8-movil`.

---

## V9 — Gestión energética avanzada ⚡
Phoenix deja de ser "control de alumbrado" y se convierte en **EMS de
infraestructura urbana**.

| Rev | Tipo | Descripción |
|---|---|---|
| R9.1 | feat | Lectura de la factura del DSO (CCH / SIPS) y conciliación |
| R9.2 | feat | Tarifas por horas, precio del mercado, optimización por coste |
| R9.3 | feat | Integración fotovoltaica / autoconsumo de instalaciones municipales |
| R9.4 | feat | Recarga de vehículo eléctrico vinculada a cuadros |
| R9.5 | feat | Reporte de huella de carbono por instalación |
| R9.6 | feat | Certificación MID y soporte para auditoría energética |

**Cierre:** snapshot `v9-ems`.

---

## Convención para añadir entradas

- Una revisión = una unidad atómica de cambio (un PR, idealmente).
- Tipos: `feat` · `fix` · `refactor` · `docs` · `test` · `ci` · `chore` · `sec` · `a11y` · `i18n`.
- Si aparece un bug en una versión cerrada, va al hito **actual** como `fix`.
- Si aparece scope nuevo, se asigna al hito temático que le toque; si no
  encaja en ninguno, abrimos un hito nuevo.

## Estado actual

- **V0 — Fundación**: en `claude/focused-volta-1zUIx` (PR #1). Próximo paso al
  cerrar: tag `v0-fundacion` y arrancar **V1 — Visual / Experiencia Phoenix**.
