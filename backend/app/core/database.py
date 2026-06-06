"""SQLAlchemy engine, session factory and declarative base.

SQLite by default (file `phoenix.db`); point PHOENIX_DATABASE_URL at Postgres
for production. `init_db()` is called on startup to create tables.
"""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

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
    from app.models import audit, cabinet, user  # noqa: F401

    Base.metadata.create_all(engine)
