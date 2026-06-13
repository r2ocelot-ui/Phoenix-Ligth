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
- **Pendiente para la próxima**
  - **Implementar el modo IA del dimming** (en curso): modelo `dimming_mode` +
    `street_profile` en Cabinet, motor `resolve_ai_level`, bucle de la bus por
    modo, endpoint `/cabinets/{id}/mode`, selector de 3 modos en Control y
    perfil de calle en la ficha del CM. Con tests.
  - **CSP estricta** (CSP-B): reconocimiento ya hecho (sin `eval`/handlers
    inline; recursos externos mapeados: unpkg, cdnjs, Google Fonts, tiles
    carto/OSM/ArcGIS, Nominatim). Falta escribir la cabecera en
    `main.py::_security_headers`.
  - Resto del backlog 🟡/🟢 en `VERSIONS.md` (JWT→cookie, ticket WS, Argon2id,
    ESIOS/REE, datos legales LICENSE/EULA…).
