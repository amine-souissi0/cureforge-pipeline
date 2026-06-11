"""In-process async task store (replace with Redis/RQ for multi-worker deployments)."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_STORE: dict[str, dict[str, Any]] = {}


def new_task_id() -> str:
    return str(uuid.uuid4())


def _put(task_id: str, state: dict[str, Any]) -> None:
    with _lock:
        _STORE[task_id] = state


def mark(task_id: str, **kwargs: Any) -> None:
    with _lock:
        if task_id in _STORE:
            _STORE[task_id].update(kwargs)


def get_snapshot(task_id: str) -> Optional[dict]:
    with _lock:
        row = _STORE.get(task_id)
        return dict(row) if row else None


def run_dispatch_task(task_id: str, task_type: str, payload: dict[str, Any], session_factory: Callable) -> None:
    """Execute orchestrator.dispatch in a worker thread (via FastAPI BackgroundTasks)."""
    from orchestrator.router import DispatchError, dispatch

    mark(task_id, status="running", error=None)
    db = session_factory()
    try:
        result = dispatch(task_type, payload, db=db)
    except DispatchError as exc:
        logger.warning("Task %s dispatch error: %s", task_id, exc)
        mark(task_id, status="failed", error=str(exc), result=None)
    except Exception as exc:
        logger.exception("Task %s failed", task_id)
        mark(task_id, status="failed", error=str(exc), result=None)
    else:
        mark(task_id, status="completed", result=result, error=None)
    finally:
        db.close()


def process_inbound_reply(
    sender_email: str,
    body_text: str,
    session_factory: Callable,
) -> None:
    """Classify reply intent and update OutreachRecord (background worker)."""
    from agents.intent_parser import parse_intent
    from models.database import OutreachRecord

    intent = parse_intent(body_text)
    logger.info(
        "Inbound reply processed",
        extra={"sender": sender_email, "intent": intent.value},
    )

    db = session_factory()
    try:
        record = db.query(OutreachRecord).filter_by(email=sender_email).first()
        if record:
            record.reply_status = intent
            record.reply_received_at = datetime.utcnow()
            record.raw_reply = body_text[:4000]
            record.pipeline_status = intent.value
            db.commit()
            logger.info("Updated OutreachRecord for %s", sender_email)
        else:
            logger.warning(
                "Received reply from unknown sender: %s — no matching record.",
                sender_email,
            )
    finally:
        db.close()


def enqueue(
    task_type: str,
    payload: dict[str, Any],
    session_factory: Callable,
    add_background_task,
) -> str:
    """Register queued task and schedule background execution."""
    task_id = new_task_id()
    _put(task_id, {"status": "queued", "result": None, "error": None})
    add_background_task(run_dispatch_task, task_id, task_type, payload, session_factory)
    return task_id
