"""Database engine and session factories.

Supports PostgreSQL (production) and SQLite (local dev fallback when
PCR_DATABASE_URL is not set or points to sqlite).
"""

from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


# Resolve URLs – fall back to SQLite if Postgres URL is default and unreachable
_db_url = settings.database_url
_db_url_sync = settings.database_url_sync

# Allow explicit SQLite override via env
if getattr(settings, "use_sqlite", False) or _db_url.startswith("sqlite"):
    _db_url = "sqlite+aiosqlite:///./data/pcr.db"
    _db_url_sync = "sqlite:///./data/pcr.db"

async_engine = create_async_engine(
    _db_url,
    echo=settings.debug,
    pool_pre_ping=not _is_sqlite(_db_url),
    connect_args={"check_same_thread": False} if _is_sqlite(_db_url) else {},
)
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

sync_engine = create_engine(
    _db_url_sync,
    echo=settings.debug,
    pool_pre_ping=not _is_sqlite(_db_url_sync),
    connect_args={"check_same_thread": False} if _is_sqlite(_db_url_sync) else {},
)
SyncSessionLocal = sessionmaker(
    sync_engine,
    class_=Session,
    expire_on_commit=False,
    autoflush=False,
)

# SQLite foreign key support
if _is_sqlite(_db_url_sync):
    @event.listens_for(sync_engine, "connect")
    def _set_sqlite_fk(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency – async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_sync_db() -> Generator[Session, None, None]:
    """Sync session for Celery tasks."""
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
