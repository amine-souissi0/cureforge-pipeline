from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from app.celery_app import celery_app
from app.schemas import AuditLog
from app.services.gmail_service import GmailService
import asyncio

router = APIRouter(prefix="/candidates", tags=["candidates"])

class WebhookPayload(BaseModel):
    message_id: str
    data: str

@celery_app.task
def process_email_task(message_id: str) -> str:
    # In a real app, this runs in a Celery worker.
    # We call the ReplyClassifier agent synchronously here or via async_to_sync
    from app.agents.reply_classifier import ReplyClassifierAgent
    import asyncio
    
    # We run the async agent in a new event loop or use an async worker
    try:
        result = asyncio.run(ReplyClassifierAgent.classify_email("MOCK_BODY", "MOCK_CONTEXT"))
        return f"Processed {message_id}: {result.intent}"
    except Exception as e:
        return f"Failed {message_id}: {str(e)}"

@router.post("/webhook")
async def gmail_webhook(payload: WebhookPayload) -> dict[str, str]:
    await AuditLog.append("api_webhook_received", {"payload": payload.model_dump()})
    
    # Trigger celery task
    process_email_task.delay(payload.message_id)
    return {"status": "accepted"}
