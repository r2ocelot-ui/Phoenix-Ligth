# Phoenix-Light · Bitácora por sesiones

> Diario **cronológico** de trabajo, una entrada por día/sesión. Sirve para
> saltar rápido a "qué hicimos el día X" sin recorrer toda la conversación.
> El **porqué** detallado va a `DECISIONS.md`; el **estado/pendientes** a
> `VERSIONS.md` y `ROADMAP.md`. Aquí: resumen del día + commits + decisiones
> + qué queda para la próxima.

Formato de cada entrada:
```
## AAAA-MM-DD · Título corto
- **Hecho**: …
- **Commits**: <hash> …
- **Decisiones**: …
- **Pendiente para la próxima**: …
```

---

## 2026-06-14 (noche) · Apagar emergencia + Búsqueda global + limpieza styles

Sesión nocturna en modo "Faro solo" mientras el capitán descansa. Backlog 🤖
del día atacado en orden de valor.

- **Hecho**
  - **Apagar emergencia** (commit `7ff151d`): nueva columna
    `Cabinet.pre_emergency_mode` + endpoints `POST /emergency/clear` y
    `GET /emergency/status`. Restaura cada cuadro a su modo previo (ai/
    schedule/manual), aplica el nivel YA via `apply_level_now`, idempotente,
    multi-tenant. Botón verde "✓ Apagar emergencia" en el menú de usuario,
    visible solo cuando hay emergencia. 1 test nuevo del ciclo completo.
  - **Búsqueda global (Ctrl+K)** (commit `3f11d87`): campo en el topbar que
    busca instantáneo en cuadros, luminarias, calles, circuitos, proyectos
    y secciones. Sin peticiones extra (usa los caches). Flechas + Enter +
    Esc + "/". Pre-carga `/topology` en segundo plano.
  - **Limpieza styles inline** (commit `5caa998`): utilitarias `.fs-11/12/13/14`
    y reemplazadas ~29 ocurrencias de `class="..." style="font-size:NNpx"`.
    Conservador: no toca los 160 `.style.X = ...` de JS.
  - **Bonus**: Cuadros gana barra superior con contador y "⬇ CSV"
    (commit `bb6031a`).
- **Pendiente para el capitán**
  - **👁️ Repaso visual** de todo lo nuevo (Ctrl+K, botón verde, exportar CSV).
  - Lista "🤝 entre los 2" sin cambios (JWT→cookie, ticket WS, Argon2id,
    cifrar totp_secret, datos legales LICENSE/EULA).

---

## 2026-06-14 · CSP estricta + iconos de ayuda + menú reordenado

- **Hecho**
  - **Logo fénix rojo** colocado: el capitán lo subió (WebP renombrado, aterrizó
    en la raíz) → lo moví a `frontend/static/phoenix-icon.png`, convertí a PNG
    real con Pillow (256px, transparente) y **agrandé** dentro del chip (menú
    50/44px, login 92/82px). Maquetas verificadas con render PIL.
  - **Decisión**: el `.exe` (PyInstaller) se hornea **por versión cuando haga
    falta**, no se desarrolla sobre él. Seguimos en código fuente. Anotado en
    el backlog.
  - **Hueco de logo PNG**: `emblemAll()` carga `frontend/static/phoenix-icon.png`
    (menú + login + favicon) y cae al emblema SVG si no existe. Decidido el
    **fénix rojo simple** para uso interno. Falta que el capitán suba el PNG.
  - **CSP estricta** (script-src sin `'unsafe-inline'`, lista cerrada de
    orígenes para script/style/font/img/connect). Cabecera servida en cada
    respuesta del backend, validada con TestClient. Test de regresión
    `test_security_headers_present`.
  - **Iconos de ayuda (?)** estilo Hydra: componente `helpIcon(tip)` con
    tooltip CSS (texto en `data-tip`, sin innerHTML). Aplicado a herramientas
    del mapa, modo del Control, perfil de calle del CM y Nominal del circuito.
  - **Menú reordenado** por uso: Operación (Inicio/Cuadros/Alarmas/Control) →
    Infraestructura (Topología/Luminarias) → Administración (Proyectos/
    Permisos/Seguridad/Auditoría).
  - Fix menor: select de rango legacy por defecto a "visualizador" (era
    "novato", alias que ya no está en el catálogo de rangos).
- **Decisiones**
  - CSP: `script-src` estricto (vector real del XSS); `style-src` queda con
    `'unsafe-inline'` porque el panel tiene ~226 `style="..."` y meterlo en
    estricto sin refactor masivo rompería el render sin ganar mucho. Lo dejo
    como pulido a futuro.
  - (HECHO 14-jun) **Saneador de color** `safeColor()` + aplicado a las 6
    interpolaciones de color con datos del backend (tablas, popup de mapa,
    pines `divIcon`, cabecera del modal del CM). Defensa en profundidad
    sobre la CSP.
  - (HECHO 14-jun) Limpieza: `loadUsers()` (la tabla huérfana de Usuarios) se
    sustituye por una redirección a la sección "Permisos". 80 líneas menos.
  - (HECHO 14-jun) **Topes de tarifa por proyecto** — backend completo:
    4 columnas opcionales en `Project`, helpers que aceptan `caps={P1,P2,P3}`,
    endpoint `GET/PUT /projects/{id}/tariff`. Auto-migración verificada (los
    proyectos viejos quedan con NULL → usan los globales). 4 tests nuevos.
    **Pendiente UI**: ficha de tarifa en Proyectos, con `helpIcon` y la
    distinción "personalizado/global".
  - (HECHO 14-jun) **UI de tarifa por proyecto**: botón "💶 Tarifa" en la
    tabla de Proyectos abre un modal con los 4 topes (placeholder muestra el
    valor global; vacío = "usar global"). Owner edita, resto solo lee.
  - (HECHO 14-jun) Rematados los últimos XSS de la auditoría: IP bans y
    eventos de seguridad.
  - (HECHO 14-jun) **Alarmas y Auditoría en español**: `ALARM_LABELS` +
    `SEVERITY_LABELS` en la tabla de alarmas; las 5 alarmas eléctricas del
    backend traducidas; `ACTION_LABELS` traduce los códigos de auditoría
    (`cabinet.create`→"Cuadro creado"…), con el código crudo en el `title`.
- **Pendiente para la próxima**
  - Limpiar progresivamente `style="..."` → clases CSS para poder endurecer
    `style-src` en una segunda vuelta.
  - Resto del bloque "🤖 yo solo" del backlog: horarios P1/P2/P3 por proyecto
    (no solo topes), rematar XSS de baja prioridad, dar las llaves al
    auto-dimming/IA, multi-proyecto FASE 2 (jerarquía zona→ciudad), fases
    lunares offline.
  - Resto del bloque 🤝 (JWT→cookie, ticket WS, Argon2id, cifrar
    `totp_secret`, datos legales) — todos marcados ⏸️ "contigo delante".

---

## 2026-06-13 · Bugs de control/topología + modo IA del dimming + memoria de proyecto

- **Hecho**
  - Fix **dimming manual**: el slider del operario ya no lo pisa el programa
    horario (modo "manual" mientras el operario manda) + flag anti-reinicio del
    slider durante el arrastre.
  - **Nominal del circuito** ahora se **auto-suma** desde las luminarias
    (read-only en UI; recompute en alta/edición/borrado).
  - Etiqueta de farola **"Farola 01"** (2 dígitos) en vez de "Farola 1.1".
  - Fix **Luminarias en blanco**: el `<option>` "Todos los cuadros" no tenía
    `value=""` → su `.value` era el texto y el filtro descartaba todo.
  - Seed: **fases concretas** (L1/L2) por circuito en vez de "III".
  - **Hotfix de arranque**: `NameError: logger` en el lifespan con TZ "auto".
  - Creada la **memoria de proyecto**: `CLAUDE.md` (índice maestro que se carga
    solo cada sesión) + este `SESIONES.md` (bitácora por día).
- **Commits**: `e096951` (5 bugs) · `a027e2f` (hotfix logger) · + memoria de proyecto.
- **Decisiones**
  - Dimming **IA = reglas offline ahora, ML después** (híbrido, detrás de una
    interfaz estable). Auditable y sin dependencias frágiles, según la filosofía
    "lo offline gana".
  - Alcance del modo IA: **el más completo** → 3 modos (Manual / Programa / IA)
    + motor IA que combina **sol + tarifa + lux + perfil de calle**, con suelo
    de seguridad por tipo de vía.
- **Hecho (cont.)** · Modo IA del dimming COMPLETO
  - Modelo: `Cabinet.dimming_mode` (manual/schedule/ai) + `street_profile`
    (arterial/residential/crossing). Auto-migración verificada en BD vieja.
  - Motor `dimming_controller.resolve_ai_level` (reglas offline, auditable):
    sol → perfil de vía → noche profunda → lux → tarifa, con suelo de seguridad.
  - Bus: `_dimming_loop` ahora va por modo (lee BD); helpers `_auto_level_for`
    y `apply_level_now` (feedback inmediato al cambiar de modo).
  - API: `POST /cabinets/{id}/mode`; `/dim` pasa el cuadro a manual; emergencia
    fija manual. 9 tests nuevos (132 verdes).
  - UI: selector de 3 modos en Control + perfil de calle en la ficha del CM.
- **Hecho (cont.)** · Pulido de topología + auditoría completa del programa
  - Fase de circuito: quitada "III" (solo L1/L2/L3) + migración de los viejos.
  - Nombre de circuito sin duplicar (`circuitLabel`); seed con nombre vacío.
  - Iconos del menú a emoji; fondo blanco del paginador (`--fg` no existía).
  - Fix dimming manual "volvía al % anterior": `try_publish` best-effort
    (registra el comando aunque no haya broker; antes 503).
  - **Auditoría completa** (2 agentes): botones/CRUD todos OK; correctness OK.
    Hallazgo P0 = **XSS sistémico** → añadido `esc()` + `cellHtml` y escapados
    ~16 sitios (nombres de CM/circuito/luminaria/proyecto, User-Agent, audit…).
  - 2 bugs funcionales: ficha de luminaria mostraba "en línea" con CM caído;
    valor 0 salía como "—".
- **Pendiente para la próxima**
  - Repasar XSS restante de baja prioridad (la auditoría citó ~200 innerHTML;
    cubiertos los de datos controlados por usuario/atacante. El helper `esc()`
    ya está para el resto).
  - Limpieza menor: tabla legacy `loadUsers`/vistas huérfanas `usuarios`+`rangos`
    (solo por deep-link; "Permisos" las reemplaza). Default de select legacy a
    "visualizador" (línea ~2398).
  - (HECHO 14-jun) **CSP estricta**: cabecera Content-Security-Policy en
    `main.py::_security_headers`. `script-src` estricto (solo 'self' + unpkg +
    cdnjs) → blinda XSS. `style-src` con 'unsafe-inline' por los 226 `style=`
    del panel (pulido futuro). Test de regresión que vigila que no se cuele
    'unsafe-inline' en script-src.
  - (HECHO 14-jun) Iconos de ayuda (?) estilo Hydra (`helpIcon`) y menú
    reordenado por uso.
  - **CSP estricta** (CSP-B): reconocimiento ya hecho (sin `eval`/handlers
    inline; recursos externos mapeados: unpkg, cdnjs, Google Fonts, tiles
    carto/OSM/ArcGIS, Nominatim). Falta escribir la cabecera en
    `main.py::_security_headers`.
  - Resto del backlog 🟡/🟢 en `VERSIONS.md` (JWT→cookie, ticket WS, Argon2id,
    ESIOS/REE, datos legales LICENSE/EULA…).
