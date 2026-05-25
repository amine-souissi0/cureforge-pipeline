import os

from celery import Celery

_redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "cureforge",
    broker=_redis_url,
    backend=_redis_url,
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
