from typing import Optional, Any
"""
FastAPI webhook server.

Receives inbound email events from Resend, parses the reply intent via GPT-4,
and updates the OutreachRecord in the database.

Optional JSON logging: set USE_JSON_LOGGING=1
Optional task API protection: set WEBHOOK_API_KEY and send header X-Webhook-Api-Key
(Resend inbound webhooks do not use WEBHOOK_API_KEY — only /tasks and /tasks/{id}.)

Run with:
    uvicorn webhook.server:app --host 0.0.0.0 --port 8000
"""

import hashlib
import hmac
import logging
import os

from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, status

from config.settings import settings
from core.logging_config import configure_json_logging
from models.database import SessionLocal, init_db
from . import tasks as task_jobs

logger = logging.getLogger(__name__)


def _require_tasks_api_key(x_webhook_api_key: Optional[str]) -> None:
    expected = (settings.webhook_api_key or "").strip()
    if not expected:
        return
    if not x_webhook_api_key or x_webhook_api_key.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Webhook-Api-Key.",
        )


def _is_local_dev() -> bool:
    return settings.local_dev or os.environ.get("LOCAL_DEV", "").lower() in ("1", "true", "yes")


@asynccontextmanager
async def lifespan(application: FastAPI):
    if settings.use_json_logging:
        configure_json_logging()
    if not _is_local_dev() and not (settings.webhook_secret or "").strip():
        logger.warning(
            "WEBHOOK_SECRET is unset outside LOCAL_DEV — /webhook will reject unsigned requests."
        )
    init_db()
    yield


app = FastAPI(title="Communication Agent Webhook", version="1.0.0", lifespan=lifespan)


def _verify_signature(payload: bytes, signature: str) -> bool:
    """
    Validate the Resend webhook HMAC-SHA256 signature.

    Resend sends the signature as: sha256=<hex_digest>
    """
    secret = (settings.webhook_secret or "").strip()
    if not secret:
        return False

    expected = (
        "sha256="
        + hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


@app.post("/webhook", status_code=status.HTTP_200_OK)
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    svix_signature: str = Header(default="", alias="svix-signature"),
    resend_signature: str = Header(default="", alias="resend-signature"),
) -> dict:
    """
    Receive an inbound email event from Resend.

    Acknowledges immediately; intent classification runs in a background task.
    """
    raw_body = await request.body()

    sig_header = (resend_signature or svix_signature or "").strip()
    if not sig_header or not _verify_signature(raw_body, sig_header):
        if _is_local_dev() and not (settings.webhook_secret or "").strip():
            logger.warning("LOCAL_DEV: accepting unsigned webhook (dev only).")
        else:
            logger.warning("Webhook signature missing or invalid.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing webhook signature.",
            )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is not valid JSON.",
        )

    event_type = payload.get("type", "")
    if event_type != "email.received":
        logger.debug("Ignoring event type: %s", event_type)
        return {"status": "ignored", "type": event_type}

    data = payload.get("data", {})
    sender_email: str = data.get("from", "").lower().strip()
    body_text: str = data.get("text") or data.get("html") or ""

    if not sender_email or not body_text:
        logger.warning("Webhook payload missing sender or body: %s", data)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing 'from' or email body in payload.",
        )

    background_tasks.add_task(
        task_jobs.process_inbound_reply,
        sender_email,
        body_text,
        SessionLocal,
    )

    return {"status": "accepted", "queued": True}


@app.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
async def submit_task(
    background_tasks: BackgroundTasks,
    request: Request,
    x_webhook_api_key: Optional[str] = Header(default=None, alias="X-Webhook-Api-Key"),
) -> dict:
    """
    Enqueue a synchronous dispatch job (runs in-process after response).

    Body: {"task_type": "grant.discover", "payload": {"keywords": "aging", "limit": 5}}
    """
    _require_tasks_api_key(x_webhook_api_key)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is not valid JSON.",
        )
    task_type = body.get("task_type")
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    if not task_type or not isinstance(task_type, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing string 'task_type'.",
        )

    task_id = task_jobs.enqueue(
        task_type,
        payload,
        SessionLocal,
        background_tasks.add_task,
    )
    logger.info("Task accepted", extra={"task_id": task_id, "task_type": task_type})
    return {"task_id": task_id, "status": "queued"}


@app.get("/tasks/{task_id}")
async def task_status(
    task_id: str,
    x_webhook_api_key: Optional[str] = Header(default=None, alias="X-Webhook-Api-Key"),
) -> dict:
    """Poll task status populated by the in-memory store."""
    _require_tasks_api_key(x_webhook_api_key)
    snap = task_jobs.get_snapshot(task_id)
    if snap is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown task_id.")
    return {"task_id": task_id, **snap}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
