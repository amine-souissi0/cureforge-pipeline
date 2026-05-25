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
def generate_task_for_candidate(self: object, candidate_id: str, role: str = "software engineer", level: str = "senior") -> str:  # noqa: ARG001
    """
    Async task: run TaskDecomposer and store result in approval queue.
    Triggered automatically when a candidate replies INTERESTED.
    """
    async def _run() -> str:
        from app.agents.task_decomposer import TaskDecomposerAgent
        from app.models import TaskModel
        from app.services.candidate_store import CandidateStore
        from app.services.task_store import TaskStore

        candidate = await CandidateStore.get_by_id(candidate_id)
        if candidate is None:
            return f"candidate_not_found:{candidate_id}"

        output = await TaskDecomposerAgent.decompose(role=role, level=level)

        if not output.success or output.blocklist_check != "PASS":
            await AuditLog.append("task_generation_rejected", {
                "candidate_id": candidate_id,
                "blocklist_check": output.blocklist_check,
            })
            return f"task_rejected:{output.blocklist_check}"

        task = TaskModel(
            candidate_id=candidate_id,
            candidate_brief=output.candidate_brief,
            internal_spec=output.internal_spec.model_dump() if output.internal_spec else {},
            corpus_ref=output.corpus_pattern_selected,
        )
        task_id = await TaskStore.add(task)

        await AuditLog.append("task_generated_async", {
            "candidate_id": candidate_id,
            "task_id": task_id,
            "corpus_ref": output.corpus_pattern_selected,
        })
        return f"task_generated:{task_id}"

    return asyncio.run(_run())


@celery_app.task(bind=True, autoretry_for=(Exception,), max_retries=3, default_retry_delay=2)  # type: ignore[misc]
def process_email_task(self: object, history_id: str) -> str:  # noqa: ARG001
    """
    Celery task: fetch all Gmail messages added since history_id,
    then run the full classification + routing pipeline for each one.
    """
    from app.services.gmail_service import GmailService
    from app.services.webhook_processor import process_inbound_message

    async def _run() -> str:
        svc = GmailService()
        messages = await svc.list_new_messages(history_id)

        if not messages:
            await AuditLog.append("process_email_task_no_messages", {
                "history_id": history_id,
            })
            return f"no_new_messages:history_id={history_id}"

        results = []
        for message in messages:
            result = await process_inbound_message(message)
            results.append(result)

        return "; ".join(results)

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


class ClassifyRequest(BaseModel):
    sender_email: str
    body: str


@router.post("/classify")
async def classify_email(payload: ClassifyRequest) -> dict:
    """
    Classify an inbound email and return the routing decision.
    Used by the founder UI 'Simulate Email' feature for testing.
    """
    from app.agents.reply_classifier import ReplyClassifierAgent, route_classified_email
    from app.services.candidate_store import CandidateStore

    candidate = await CandidateStore.get_by_email(payload.sender_email)
    candidate_context = (
        f"name={candidate.name}, state={candidate.state}"
        if candidate else "unknown candidate"
    )

    output = await ReplyClassifierAgent.classify_email(
        email_body=payload.body,
        candidate_context=candidate_context,
    )
    routing = route_classified_email(output, candidate.id if candidate else "unknown")

    await AuditLog.append("email_classified_manual", {
        "sender_email": payload.sender_email,
        "intent": output.intent,
        "confidence": output.confidence,
        "routing": routing,
    })

    return {
        "intent": output.intent,
        "confidence": output.confidence,
        "extracted": output.extracted,
        "summary": output.summary,
        "routing": routing,
        "candidate_found": candidate is not None,
    }


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


@oauth_router.get("/status")
async def oauth_status() -> dict:
    import os
    from app.config import GOOGLE_TOKEN_FILE
    token_json = os.environ.get("GMAIL_TOKEN_JSON", "")
    if token_json:
        return {"connected": True, "source": "env"}
    connected = os.path.exists(GOOGLE_TOKEN_FILE)
    return {"connected": connected, "source": "file" if connected else None}
