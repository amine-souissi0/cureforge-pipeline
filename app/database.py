import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# Dev default: SQLite. Production: set DATABASE_URL=postgresql+asyncpg://...
# Railway gives postgres:// or postgresql:// — normalise to asyncpg dialect.
_raw_db_url: str = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./cureforge.db")
if _raw_db_url.startswith("postgres://"):
    _raw_db_url = _raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw_db_url.startswith("postgresql://") and "+asyncpg" not in _raw_db_url:
    _raw_db_url = _raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
DATABASE_URL: str = _raw_db_url

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    # SQLite-specific: allow the same connection across threads
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Create all tables. Safe to call multiple times (CREATE IF NOT EXISTS)."""
    import app.orm_models  # noqa: F401 — registers all ORM models with Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
