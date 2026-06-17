# Phoenix-Light · Roadmap

Pendientes ordenados por prioridad. Cada entrada apunta a la decisión en
`docs/DECISIONS.md` cuando hay diseño previo apuntado.

> 📍 **Este archivo es el índice del proyecto.** En vez de buscar en el
> chat, mira aquí: arriba lo hecho (✅), abajo lo pendiente por prioridad.
> Última actualización: 2026-06 · 67/67 tests verdes.

---

## 🟢 Listo y desplegado

**Seguridad / acceso**
- ✅ **Login en 2 pasos obligatorios** (usuario + contraseña + PIN → patrón)
- ✅ **Anti-keylogger** (cambio de credencial pide la actual)
- ✅ **Auto-ban por IP** (fail2ban-style, persistente)
- ✅ **Banlist gestionable** desde el panel
- ✅ **Modo siege** (solo IPs whitelisted, owner-only)
- ✅ **Dispositivos del usuario** (cookie + lista + revocar)
- ✅ Historial de seguridad (admin-only) con KPIs 24h
- ✅ Lockout por usuario + cuenta atrás de inactividad

**Roles / multi-tenant**
- ✅ **Jerarquía Hydra-style** de 7 rangos (sin admin_programa)
- ✅ **Editor de rangos** (catálogo en BD, permisos editables, layout vertical)
- ✅ **Multi-tenant activo** (admin solo ve su proyecto)
- ✅ **Selector "Ciudad activa"** en topbar (estilo Hydra)
- ✅ **Vista Permisos unificada** (Usuarios + Rangos en una pestaña)
- ✅ Usuarios/Rangos/Seguridad solo visibles para admin/owner

**Operación / alarmas**
- ✅ **Inicio = mapa operativo** (estilo Hydra, sin "palpito")
- ✅ **Dock flotante de eventos** abajo derecha, filtrado por rol
- ✅ **Alarmas eléctricas**: LAMP_OUT, LINE_FAILURE, OVER/UNDERVOLTAGE, OVERCURRENT
- ✅ **Alarmas físicas del CM**: puerta abierta, temperatura alta, intrusión
- ✅ **Alarmas de consumo (matriz §6.6)**: carga caída, sobrecarga, contactor pegado
- ✅ **Nominal `expected_power_w` por circuito** (editable por API)
- ✅ Modo emergencia (todo ON al 100% en un clic)
- ✅ **Topología compacta** (grid de tarjetas + buscador, escala a 100+ CMs)
- ✅ Paginación en Auditoría e Historial de seguridad

**Infraestructura**
- ✅ **Vinculación hardware SICE-style** (serial + IMEI por cuadro, backend)
- ✅ **Borrar CM / circuito / wipe-all** (backend con cascada + auditoría)
- ✅ **Auto-migración del schema** (no hay que borrar `phoenix.db`)
- ✅ **Editor de topología (UI)** — crear/editar/borrar CM, circuitos y
  luminarias desde el panel, con nominal `expected_power_w` editable
- ✅ **Añadir CM clicando el mapa** (estilo Hydra, captura lat/lon)
- ✅ **Eliminar usuarios** (con anti-autoborrado y anti-escalado)
- ✅ Footer anclado abajo del todo, centrado

---

## 🟡 Prioridad alta — siguiente sesión

### 1. 2FA TOTP estilo Google Authenticator
Cuarta credencial encima de contraseña + PIN + patrón. Activable por
usuario. Endpoint `/auth/totp/setup` con QR + `/auth/totp/verify` en el
flujo de login. Librería: `pyotp`.
*Diseño:* DECISIONS §1.8.

### 2. Pestaña "Proyectos" en el panel
Los endpoints `/projects` ya existen (CRUD + assign-user + assign-cabinet),
pero falta la UI dedicada para el owner. Lista de proyectos, botón crear,
panel detalle con usuarios y cuadros asignados, botón para mover.

### 3. Pestaña "Dispositivos" (vinculación SICE)
Igual: endpoints `/devices` listos. Falta UI para registrar serial + IMEI
contra un cuadro y ver `last_seen_at`. Marcaría también
`security.device_mismatch` si se detecta.

### 4. Visualizar telemetría infra en el panel del cuadro
Temperatura, puerta, intrusión ya llegan al backend (`Measurement`).
Falta pintarlas en el popup/detalle del CM (ahora solo se ven V/I).
También las luminarias clicables en el mapa (hoy solo el CM).

---

## 🔵 Prioridad media

### 6. Identidad visual V1
- Logo Phoenix animado en login y header.
- Iconos de farola SVG propios (no Leaflet por defecto).
- Paleta más coherente (las severities ok/warn/bad ya están definidas).
- Tipografía: pendiente elegir entre algo industrial o algo más limpio.

### 7. Anti-copia / licensing del software
Para evitar que alguien clone el código y arranque su propio Phoenix
fuera de los clientes legítimos.
- Server fingerprint (hostname + MAC).
- Licencia firmada (HMAC-SHA256 con secreto compartido).
- Sin licencia válida → modo "no licenciado" (solo lectura).
- Atado a la huella del servidor.
*Trabajo serio:* ~1 sesión completa.

### 8. Editor de **permisos individuales** por usuario
Hoy un admin puede cambiar el rango entero, pero no añadir/quitar
permisos a un usuario concreto desde la UI. El endpoint existe
(`/users/{id}/permissions`). Falta UI: dos chips (extra / denegados)
en la fila expandida del usuario en `Permisos`.

### 9. Filtrado por proyecto de auditoría y banlist
Hoy `/audit/security` y `/security/bans` son globales. Decidir si un
admin de proyecto ve solo eventos de SU proyecto o todo. Probablemente
sí filtrar.

### 10. Histórico de consumos / averías
Persistir la telemetría (hoy solo vive en memoria del bus). Tabla
`measurements` + gráficos de consumo por circuito/día. Base para la
detección de tendencias (luminarias que se degradan poco a poco).

---

## 🟣 Prioridad baja / futuro

### 11. Hardware real
Cuando llegue el primer despliegue físico (ver DECISIONS §6.3 para el
diseño eléctrico completo del CM Phoenix CM-P1):

**Fase 1 · Cuadro abierto con PLC + telemetría por circuito:**
- PLC **Phoenix Contact PLCnext AXC F 2152** + módulos Axioline DI/DO.
- Fuente 24 V DC + relés intermedios 24 V DC para aislar PLC ↔ bobinas
  230 V AC de los contactores. **Nunca cablear PLC → bobina directo.**
- Analizador de red trifásico Modbus (Socomec DIRIS A-40 / Carlo
  Gavazzi EM340) + 3 TIs.
- Router 4G industrial Teltonika RUT241 + switch DIN.
- Lógica orden + confirmación + consumo (la matriz de DECISIONS §6.3
  detecta: contactor no cerró, contactor pegado, línea caída).
- Firmware del PLC publica vía **MQTT** los topics que el bus de
  Phoenix-Light ya consume (`phoenix/cabinets/<code>/telemetry`,
  `/status`, `/cmd/...`).

**Fase 2 · Edge en el gateway:**
- Raspberry Pi 5 + Hailo-8 HAT en el centro de mando.
- Phoenix-Light corre ahí, recibe MQTT de todos los CMs.

**Fase 3 · Detección luminaria-a-luminaria (futuro):**
- DALI si es instalación nueva.
- LoRa/NB-IoT si es retrofit.
- PLC por línea (narrowband sobre cableado eléctrico) si no hay otra.

### 12. ML — Predicción de consumo
- Servicio aislado (mismo Python) que entrena un modelo sobre el
  histórico de telemetría (requiere antes el #10, histórico persistido).
- Predice el consumo de la noche siguiente.
- Alerta si la realidad se desvía X% del predicho (posible avería).
*Cuando haya histórico real de varios meses.*

### 13. Migración Hydra Traffic Lab a Python
Si llega ese trabajo: TypeScript/Node → Python/FastAPI manteniendo el
schema SQL. *Decisión sobre la conveniencia: DECISIONS §5.2.*

### 14. Frontend a React/TypeScript
Cuando el front en vanilla JS empiece a doler, pasarlo a React + TS
manteniendo el backend Python. *Combo industria estándar.*

### 15. Identidad visual V2: dashboards con gráficos
- Consumo por hora/día/semana.
- Comparativa entre cuadros.
- Heatmap de alarmas por zona/mes.

---

## 🛡️ Mantenimiento continuo

- Mantener tests verdes en cada PR (actual: **67/67**).
- `docs/DECISIONS.md` se actualiza con CADA decisión que sobreviva entre
  sesiones — es el cerebro a largo plazo del proyecto.
- Este `ROADMAP.md` se va vaciando arriba (✅) y reordenando abajo
  conforme las prioridades cambien.

---

## 🤝 Reparto del proyecto (acordado en chat, con humor)
- **Cerebro / visión de producto:** 50% usuario · 50% Claude.
- **Manos / código:** 30% usuario · 70% Claude.
- En la práctica: el usuario marca el rumbo y detecta agujeros; Claude
  implementa, documenta y recuerda lo pendiente. 🔥
