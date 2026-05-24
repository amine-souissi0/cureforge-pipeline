import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from app.celery_app import celery_app
from app.fsm import CandidateState, FSMEngine
from app.schemas import AuditLog

router = APIRouter(prefix="/candidates", tags=["candidates"])
oauth_router = APIRouter(prefix="/oauth", tags=["oauth"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class IntakeRequest(BaseModel):
    name: str
    email: str
    github_handle: Optional[str] = None
    source: str = "founder_added"


class WebhookPayload(BaseModel):
    """Gmail Pub/Sub push notification envelope."""
    message: dict
    subscription: str


class ApprovalPayload(BaseModel):
    candidate_id: str
    approved: bool
    reviewer: str = "founder"


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, autoretry_for=(Exception,), max_retries=3, default_retry_delay=2)  # type: ignore[misc]
def process_email_task(self: object, gmail_message_id: str) -> str:  # noqa: ARG001
    from app.agents.reply_classifier import ReplyClassifierAgent, route_classified_email
    from app.services.gmail_service import GmailService

    async def _run() -> str:
        svc = GmailService()
        messages = await svc.poll_messages(max_results=1)

        if not messages:
            return f"No message found for {gmail_message_id}"

        msg = messages[0]
        output = await ReplyClassifierAgent.classify_email(
            email_body=msg.body,
            candidate_context=msg.candidate_id,
        )

        routing = route_classified_email(output, msg.candidate_id)
        await AuditLog.append("email_routed", {
            "gmail_message_id": gmail_message_id,
            "candidate_id": msg.candidate_id,
            "intent": output.intent,
            "confidence": output.confidence,
            "routing": routing,
        })

        if routing == "fsm_withdrawn":
            fsm = FSMEngine()
            await fsm.transition(
                candidate_id=msg.candidate_id,
                target_state=CandidateState.WITHDRAWN,
                context={"intent": "DECLINE"},
                actor="reply_classifier",
            )

        return f"Processed {gmail_message_id}: {output.intent} → {routing}"

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@router.post("/intake")
async def intake_candidate(payload: IntakeRequest) -> dict:
    """Add a new candidate and transition them to ENGAGED."""
    from app.models import CandidateModel

    try:
        candidate = CandidateModel(
            name=payload.name,
            email=payload.email,
            github_handle=payload.github_handle,
            source=payload.source,  # type: ignore[arg-type]
        )
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    from app.services.candidate_store import CandidateStore
    await CandidateStore.add(candidate)

    fsm = FSMEngine()
    transitioned = await fsm.transition(
        candidate_id=candidate.id,
        target_state=CandidateState.ENGAGED,
        context={"intake_complete": True},
        actor="intake_api",
    )

    if transitioned:
        await CandidateStore.update_state(candidate.id, CandidateState.ENGAGED)

    await AuditLog.append("candidate_intake", {
        "candidate_id": candidate.id,
        "email": candidate.email,
        "fsm_transitioned": transitioned,
    })

    return {"candidate_id": candidate.id, "state": "ENGAGED" if transitioned else "NEW"}


@router.post("/webhook")
async def gmail_webhook(payload: WebhookPayload) -> dict:
    """Receive Gmail Pub/Sub push notifications."""
    from app.services.gmail_service import GmailService

    await AuditLog.append("api_webhook_received", {"subscription": payload.subscription})
    svc = GmailService()
    await svc.handle_webhook(payload.model_dump())
    return {"status": "accepted"}


@router.post("/approve")
async def approve_draft(payload: ApprovalPayload) -> dict:
    """Founder approves or rejects a draft outbound email."""
    await AuditLog.append("draft_decision", {
        "candidate_id": payload.candidate_id,
        "approved": payload.approved,
        "reviewer": payload.reviewer,
    })
    return {"candidate_id": payload.candidate_id, "approved": payload.approved}


# ---------------------------------------------------------------------------
# OAuth routes
# ---------------------------------------------------------------------------

@oauth_router.get("/start")
async def oauth_start() -> dict:
    from app.services.gmail_service import GmailService
    try:
        url = await GmailService.get_oauth_url()
        return {"auth_url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@oauth_router.get("/callback")
async def oauth_callback(code: str) -> dict:
    from app.services.gmail_service import GmailService
    try:
        await GmailService.complete_oauth(code)
        return {"status": "authenticated"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
