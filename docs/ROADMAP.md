# Phoenix-Light · Roadmap

Pendientes ordenados por prioridad. Cada entrada apunta a la decisión en
`docs/DECISIONS.md` cuando hay diseño previo apuntado.

---

## 🟢 Listo y desplegado

- ✅ **Login en 2 pasos obligatorios** (usuario + contraseña + PIN → patrón)
- ✅ **Anti-keylogger** (cambio de credencial pide la actual)
- ✅ **Auto-ban por IP** (fail2ban-style, persistente)
- ✅ **Banlist gestionable** desde el panel
- ✅ **Modo siege** (solo IPs whitelisted, owner-only)
- ✅ **Dispositivos del usuario** (cookie + lista + revocar)
- ✅ **Vinculación hardware SICE-style** (serial + IMEI por cuadro)
- ✅ **Jerarquía Hydra-style** de 7 rangos (sin admin_programa)
- ✅ **Editor de rangos** (catálogo en BD, permisos editables)
- ✅ **Multi-tenant activo** (admin solo ve su proyecto)
- ✅ **Selector "Ciudad activa"** en topbar (estilo Hydra)
- ✅ **Vista Permisos unificada** (Usuarios + Rangos en una pestaña)
- ✅ **Inicio = mapa operativo** (estilo Hydra)
- ✅ **Dock flotante de eventos** abajo derecha
- ✅ **Auto-migración del schema** (no hay que borrar `phoenix.db`)
- ✅ Historial de seguridad (admin-only) con KPIs 24h
- ✅ Lockout por usuario + cuenta atrás de inactividad
- ✅ Modo emergencia (todo ON al 100% en un clic)

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

---

## 🔵 Prioridad media

### 4. Identidad visual V1
- Logo Phoenix animado en login y header.
- Iconos de farola SVG propios (no Leaflet por defecto).
- Paleta más coherente (las severities ok/warn/bad ya están definidas).
- Tipografía: pendiente elegir entre algo industrial o algo más limpio.

### 5. Anti-copia / licensing del software
Para evitar que alguien clone el código y arranque su propio Phoenix
fuera de los clientes legítimos.
- Server fingerprint (hostname + MAC).
- Licencia firmada (HMAC-SHA256 con secreto compartido).
- Sin licencia válida → modo "no licenciado" (solo lectura).
- Atado a la huella del servidor.
*Trabajo serio:* ~1 sesión completa.

### 6. Editor de **permisos individuales** por usuario
Hoy un admin puede cambiar el rango entero, pero no añadir/quitar
permisos a un usuario concreto desde la UI. El endpoint existe
(`/users/{id}/permissions`). Falta UI: dos chips (extra / denegados)
en la fila expandida del usuario en `Permisos`.

### 7. Filtrado por proyecto de auditoría y banlist
Hoy `/audit/security` y `/security/bans` son globales. Decidir si un
admin de proyecto ve solo eventos de SU proyecto o todo. Probablemente
sí filtrar.

---

## 🟣 Prioridad baja / futuro

### 8. Hardware real
Cuando llegue el primer despliegue físico:
- ESP32-S3 en cuadros con firmware que publique MQTT.
- Raspberry Pi 5 + Hailo-8 como gateway por defecto (DECISIONS §6).
- Drivers `pymodbus` para hablar con contadores.

### 9. ML — Predicción de consumo
- Servicio aislado (mismo Python) que entrena un modelo sobre el
  histórico de telemetría.
- Predice el consumo de la noche siguiente.
- Alerta si la realidad se desvía X% del predicho (posible avería).
*Cuando haya histórico real de varios meses.*

### 10. Migración Hydra Traffic Lab a Python
Si llega ese trabajo: TypeScript/Node → Python/FastAPI manteniendo el
schema SQL. *Decisión sobre la conveniencia: DECISIONS §5.2.*

### 11. Frontend a React/TypeScript
Cuando el front en vanilla JS empiece a doler, pasarlo a React + TS
manteniendo el backend Python. *Combo industria estándar.*

### 12. Identidad visual V2: dashboards con gráficos
- Consumo por hora/día/semana.
- Comparativa entre cuadros.
- Heatmap de alarmas por zona/mes.

---

## 🛡️ Mantenimiento continuo

- Mantener tests verdes en cada PR (actual: 57/57).
- `docs/DECISIONS.md` se actualiza con CADA decisión que sobreviva entre
  sesiones — es el cerebro a largo plazo del proyecto.
- Este `ROADMAP.md` se va vaciando arriba (✅) y reordenando abajo
  conforme las prioridades cambien.
