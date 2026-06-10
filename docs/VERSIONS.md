# Phoenix-Light · Revisiones verificadas

Registro de revisiones. Una revisión solo se marca **✅ OK** cuando el
capitán la ha probado en pantalla y funciona. Hasta entonces queda
🧪 (verificada por Faro: tests + smoke + lint) o 🔨 (en curso).

## Cómo verificamos (doble visto bueno)
Cada bloque necesita **las dos** verificaciones para pasar a ✅ OK:
1. 🧪 **Faro**: tests backend + smoke de endpoints + lint de JS.
2. 👁️ **Capitán**: lo prueba en pantalla y confirma que se ve y funciona.

Si ambas salen bien → ✅ OK. Si una falla → se queda 🩹 con notas hasta
arreglarlo.

## Leyenda de estados
- 🔨 **En curso** — se está construyendo.
- 🧪 **Faro OK** — pasa tests + smoke + lint. Falta la del capitán.
- ✅ **OK** — las dos verificaciones (Faro + Capitán) pasan.
- 🩹 **Con notas** — funciona pero hay ajustes pendientes (se listan).

> Faro NO puede ver el render del navegador: valida código y backend.
> La verificación visual la hace siempre el capitán.

---

## R1 — Base operativa completa  ·  🧪 pendiente de verificación visual

Acumulado hasta 2026-06-10. Todo pasa 79/79 tests + smoke + JS lint.
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
("el login OK", "la topología OK"…) y lo paso a ✅ aquí. Cuando todos
estén ✅, cerramos **R1** y abrimos **R2** para lo siguiente.

---

## Plantilla para próximas revisiones

```
## R{n} — {título}  ·  {estado}
Fecha · resumen.
| Bloque | Estado | Qué probar |
```
