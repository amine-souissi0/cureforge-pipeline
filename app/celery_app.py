import asyncio
import os

from celery import Celery
from celery.signals import worker_process_init

_redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "cureforge",
    broker=_redis_url,
    backend=_redis_url,
    include=["app.api.candidates"],
)


@worker_process_init.connect
def reset_db_engine(**kwargs):
    """Replace the engine with NullPool after forking.
    asyncpg connections from the parent process cannot be reused in child processes."""
    import sqlalchemy
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    import app.database as db

    db.engine = create_async_engine(
        db.DATABASE_URL,
        poolclass=sqlalchemy.pool.NullPool,
        connect_args={"check_same_thread": False} if db.DATABASE_URL.startswith("sqlite") else {},
    )
    db.AsyncSessionLocal = async_sessionmaker(
        db.engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "renew-gmail-watch": {
            "task": "app.api.candidates.renew_gmail_watch",
            "schedule": 6 * 24 * 60 * 60,  # every 6 days (watch expires at 7)
        },
    },
)
