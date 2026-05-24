import os
import re
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Wire in our ORM models so autogenerate can see them
import app.orm_models  # noqa: F401
from app.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url(url: str) -> str:
    """Convert async driver URL to sync for Alembic (which is sync-only)."""
    url = re.sub(r"^sqlite\+aiosqlite", "sqlite", url)
    url = re.sub(r"^postgresql\+asyncpg", "postgresql", url)
    return url


def get_url() -> str:
    db_url = os.environ.get("DATABASE_URL", "sqlite:///./cureforge.db")
    return _sync_url(db_url)


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
