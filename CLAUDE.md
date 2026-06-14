# Phoenix-Light · Guía para Faro (se carga sola cada sesión)

> Este archivo lo lee Claude Code **automáticamente al arrancar cada sesión**.
> Es el **índice maestro**: en vez de recorrer la conversación, mira aquí y
> salta al documento que toque. Mantenerlo corto y actualizado.

## Quiénes somos
- **Faro** — el asistente (yo). Implemento, pruebo y documento.
- **Capitán** — Angel Eduardo (`r2ocelot@gmail.com`), titular del proyecto.
- **Kumiho** — empresa matriz. Hermanos del ecosistema: **Hydra** (tráfico),
  **Argus** (CCTV), **Osiris** (residuos). Phoenix = **alumbrado público**.

## Qué es Phoenix-Light
Plataforma de **telegestión y eficiencia de alumbrado público** (cuadros de
mando → circuitos → luminarias), estilo Citilux/RF-Light pero endurecida.
Backend FastAPI + MQTT; panel web de una sola página.

## Dónde mirar (índice de documentación)
| Archivo | Para qué |
|---|---|
| `docs/VERSIONS.md` | **Estado y backlog** con verificación 🧪/👁️. La lista que más se mira |
| `docs/ROADMAP.md` | Índice por prioridad (hecho ✅ arriba, pendiente abajo) |
| `docs/DECISIONS.md` | El **porqué** de cada decisión, por temas, con fecha |
| `docs/SESIONES.md` | **Bitácora por día/sesión** — qué se hizo cada jornada |
| `docs/PRUEBAS-NAVEGADOR.md` | Recetas F12 → Console para probar endpoints sin clicar |
| `docs/SMARTCITY-BUS.md` | Visión V2 del bus compartido del ecosistema |
| `docs/HYDRA-SECURITY-NOTES.md` | Notas de seguridad para la sesión de Hydra |
| `LICENSE` / `docs/EULA.md` | Licencia Ed25519 + EULA (datos legales pendientes) |

## Flujo de trabajo (git)
- Rama de desarrollo: **`claude/focused-volta-1zUIx`**. No pushear a otra sin permiso.
- `git push -u origin claude/focused-volta-1zUIx` (reintentos con backoff si falla por red).
- Tras pushear, abrir/actualizar **PR en draft** si no existe.
- Mensajes de commit **en español**, claros, y terminan con el enlace de sesión.
- **NUNCA** poner la identidad del modelo (claude-opus-…) en commits, PR, código ni docs. Solo en el chat.

## Cómo verificamos (doble visto bueno)
- 🧪 **Faro**: `cd backend && python -m pytest -q` + `node --check frontend/app.js`.
- 👁️ **Capitán**: lo prueba en pantalla (Faro NO ve el render del navegador).
- Estados: 🔴 urgente · 🟡 prioritario · 🟢 no urgente · 🔨 en curso ·
  🧪 Faro OK · 🔵 cerrado (Faro+capitán) · ⚪ aparcado.

## Stack y estructura
- **Backend**: FastAPI + SQLAlchemy 2.0 + SQLite (Postgres en prod) + MQTT (aiomqtt).
  - `backend/app/api/v1/` endpoints · `core/` (config, db, mqtt_client, seguridad, tz, version)
  - `services/` (alarm_engine, dimming_controller, sun, tariff, tenancy, ranks, …)
  - `models/` ORM · `schemas/` Pydantic
- **Frontend**: `frontend/index.html` + `frontend/app.js` (JS extraído, sin inline) + Leaflet (CDN).
- **Migraciones**: ligeras y aditivas en `core/database.py::_autopatch_columns` (añade columnas nuevas solas; nunca borra). Funciones `_migrate_*` para datos heredados.

## Comandos clave
```bash
# tests backend
cd backend && python -m pytest -q
# lint del frontend (desde la raíz del repo)
node --check frontend/app.js
# arrancar en local
cd backend && uvicorn app.main:app --reload    # panel en http://localhost:8000/ui/
```

## Demo / credenciales
- Modo demo siembra owner **phoenix** / contraseña **phoenix123** / PIN **1234** / patrón **01258** (Z diagonal) + 4 cuadros en Madrid.

## Reglas de seguridad acordadas (no romper)
- El **2FA NO se desactiva** desde administración: solo se **regeneran** los códigos de recuperación.
- Reset de contraseña/PIN/patrón **solo sobre rangos estrictamente inferiores**.
- Rangos: visualizador→operador→técnico→supervisor→ingeniero→**admin_proyecto ("Director")**→**owner ("Phoenix")**. `*` = permiso global.
- Multi-tenant por `project_id` (+ `project_ids` N:N): el **rango dice qué**, el **proyecto dice dónde**.
- Filosofía: **lo offline gana** a lo que necesita internet. Nada de dependencias frágiles.
