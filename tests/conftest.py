import asyncio
import os

# Must be set before any app module is imported so the async engine
# uses the test database instead of cureforge.db.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./cureforge_test.db")

import pytest


@pytest.fixture(scope="session", autouse=True)
def init_test_database():
    """Drop and recreate all tables once per test session using the test SQLite file."""
    from app.database import engine, Base
    import app.orm_models  # noqa: F401

    async def _reset():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.get_event_loop().run_until_complete(_reset())
