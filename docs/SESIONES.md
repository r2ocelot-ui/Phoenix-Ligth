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
- **Pendiente para la próxima**
  - **CSP estricta** (CSP-B): reconocimiento ya hecho (sin `eval`/handlers
    inline; recursos externos mapeados: unpkg, cdnjs, Google Fonts, tiles
    carto/OSM/ArcGIS, Nominatim). Falta escribir la cabecera en
    `main.py::_security_headers`.
  - Resto del backlog 🟡/🟢 en `VERSIONS.md` (JWT→cookie, ticket WS, Argon2id,
    ESIOS/REE, datos legales LICENSE/EULA…).
