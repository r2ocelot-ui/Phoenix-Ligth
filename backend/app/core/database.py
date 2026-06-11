"""SQLAlchemy engine, session factory and declarative base.

SQLite by default (file `phoenix.db`); point PHOENIX_DATABASE_URL at Postgres
for production. `init_db()` is called on startup to create tables.
"""
import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger("phoenix.db")

_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Import models so their tables register on Base.metadata before create_all.
    from app.models import (  # noqa: F401
        audit, cabinet, circuit, device, lightpoint, project, role, security, user,
    )

    Base.metadata.create_all(engine)
    _autopatch_columns()
    _migrate_legacy_ranks()
    _migrate_legacy_admin()
    _migrate_user_projects()


def reconcile_legacy_admin(db) -> str:
    """Reconcilia el usuario demo heredado ``admin`` (anterior al cambio de
    nombre a ``phoenix``):

    - Si NO existe ``phoenix`` → renombra ``admin`` → ``phoenix`` (conserva id,
      contraseña y credenciales). Devuelve ``"renamed"``.
    - Si YA existe ``phoenix`` y queda un ``admin`` heredado → es el sobrante
      del cambio de nombre. En **modo demo** se elimina (devuelve ``"deleted"``);
      en producción NO se toca por si ``admin`` fuese una cuenta real
      (``"kept"``).

    Idempotente. Devuelve ``"noop"`` si no hay ``admin``."""
    from app.models.user import User
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        return "noop"
    phoenix = db.query(User).filter(User.username == "phoenix").first()
    if phoenix is None:
        admin.username = "phoenix"
        db.commit()
        logger.info("Renombrado usuario heredado 'admin' → 'phoenix'")
        return "renamed"
    # Conviven ambos (residuo del cambio de nombre). Solo se reconcilia en demo;
    # en producción no tocamos cuentas por si 'admin' fuese real.
    if not settings.demo_mode:
        return "kept"
    if admin.id < phoenix.id:
        # 'admin' es el más antiguo (id menor): lo conservamos como 'phoenix'
        # para MANTENER ese id, y borramos el 'phoenix' duplicado más nuevo.
        db.delete(phoenix)
        db.commit()
        admin.username = "phoenix"
        db.commit()
        logger.info("Promovido 'admin' heredado → 'phoenix' (conserva id %s)", admin.id)
        return "promoted"
    # 'phoenix' ya es el más antiguo: solo limpiamos el 'admin' sobrante.
    db.delete(admin)
    db.commit()
    logger.info("Eliminado usuario demo heredado 'admin' (ya existe 'phoenix')")
    return "deleted"


def _migrate_legacy_admin() -> None:
    with SessionLocal() as db:
        reconcile_legacy_admin(db)


def _migrate_user_projects() -> None:
    """Rellena ``project_ids`` (multi-proyecto) a partir del ``project_id``
    único existente, para usuarios que aún no lo tengan. Idempotente."""
    from app.models.user import User
    with SessionLocal() as db:
        changed = 0
        for u in db.query(User).all():
            if not (u.project_ids or []) and u.project_id is not None:
                u.project_ids = [u.project_id]
                changed += 1
        if changed:
            db.commit()
            logger.info("Multi-proyecto: inicializado project_ids en %d usuario(s)", changed)


def _migrate_legacy_ranks() -> None:
    """Rename users still on old rank IDs to their new counterparts so older
    databases keep working after the 7-tier refactor (novato → visualizador,
    admin → admin_proyecto, ...). Idempotent: a second run is a no-op."""
    from app.services.ranks import LEGACY_ALIASES
    if not LEGACY_ALIASES:
        return
    with engine.begin() as conn:
        for old, new in LEGACY_ALIASES.items():
            result = conn.execute(
                text('UPDATE users SET rank = :new WHERE rank = :old'),
                {"new": new, "old": old},
            )
            if result.rowcount:
                logger.info("Migrated %d user(s) from rank %r → %r",
                            result.rowcount, old, new)


def _autopatch_columns() -> None:
    """Lightweight forward migrations: add columns that exist on the model but
    not yet in the database. Saves users from manually deleting ``phoenix.db``
    every time the schema grows. Only adds — never drops or alters types.
    """
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            try:
                ddl = _column_add_ddl(table.name, column)
            except ValueError:
                logger.warning("Skipping migration for %s.%s — manual review needed",
                               table.name, column.name)
                continue
            with engine.begin() as conn:
                conn.execute(text(ddl))
            logger.info("Auto-migration: added %s.%s", table.name, column.name)


def _column_add_ddl(table_name: str, column) -> str:
    """Build a safe ``ALTER TABLE ... ADD COLUMN`` for an additive change.
    Refuses NOT NULL columns without a default (those need a real migration)."""
    col_type = column.type.compile(dialect=engine.dialect)
    parts = [f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {col_type}']
    if column.default is not None and getattr(column.default, "arg", None) is not None:
        default = column.default.arg
        if isinstance(default, (int, float)):
            parts.append(f"DEFAULT {default}")
        elif isinstance(default, str):
            parts.append(f"DEFAULT '{default}'")
        elif default is False:
            parts.append("DEFAULT 0")
        elif default is True:
            parts.append("DEFAULT 1")
    elif not column.nullable:
        raise ValueError("NOT NULL without default")
    return " ".join(parts)
