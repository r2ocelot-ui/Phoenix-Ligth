# Phoenix-Light · Revisiones verificadas

Registro de revisiones. Una revisión solo se marca **🔵 OK** cuando el
capitán la ha probado en pantalla y funciona. Hasta entonces queda
🧪 (verificada por Faro: tests + smoke + lint) o 🔨 (en curso).

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

---

## R1 — Base operativa completa  ·  🧪 pendiente de verificación visual

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
estén 🔵, cerramos **R1** y abrimos **R2** para lo siguiente.

---

## R2 — Hardening de seguridad y release  ·  🧪 en marcha

### 🔴 Hecho hoy
| Bloque | Estado | Qué probar |
|---|---|---|
| Multi-tenant en `/cabinets/{id}/relay`, `/dim`, `/emergency/all-on` | 🧪 | Un operador de Madrid no debe poder tocar cuadros de Barcelona (404, sin leak) |
| WebSocket `/ws` valida usuario + permiso + scope | 🧪 | Desactivar un usuario → su WS se cierra; un user de Madrid solo ve sus cuadros en el snapshot |
| Guard de producción del `jwt_secret` | 🧪 | Arrancar con `PHOENIX_DEMO_MODE=false` y `jwt_secret` por defecto → revienta el arranque |
| `tools/make_release.py` (paquete limpio estilo Hydra) | 🧪 | `python3 tools/make_release.py` → `dist/phoenix-cliente-<fecha>.zip` sin `.git/.venv/.db/tests` |
| `services/sun.py` + endpoint `/cabinets/{id}/sun` | 🧪 | Sunrise/sunset astronómico OFFLINE para sanity-check de la fotocélula |

### 🔴 Pendiente urgente
| Bloque | Estado | Qué pasa |
|---|---|---|
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

---

## Plantilla para próximas revisiones

```
## R{n} — {título}  ·  {estado}
Fecha · resumen.
| Bloque | Estado | Qué probar |
```
