"""Setup SQLAlchemy: engine, session factory, dan dependency ``get_db``.

Session dikelola dengan ``try/finally`` sehingga selalu ditutup, mencegah
kebocoran koneksi (connection leak) pada pool.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# ``check_same_thread`` hanya relevan untuk SQLite.
_connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,  # buang koneksi mati sebelum dipakai
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base declarative untuk seluruh model ORM."""


def get_db() -> Generator[Session, None, None]:
    """Dependency FastAPI: sediakan sesi DB dan pastikan selalu tertutup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
