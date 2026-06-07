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
    from app.models import audit, cabinet, circuit, lightpoint, user  # noqa: F401

    Base.metadata.create_all(engine)
    _autopatch_columns()


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
