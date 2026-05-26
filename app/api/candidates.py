import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from app.celery_app import celery_app
from app.fsm import CandidateState, FSMEngine
from app.schemas import AuditLog


router = APIRouter(prefix="/candidates", tags=["candidates"])
oauth_router = APIRouter(prefix="/oauth", tags=["oauth"])
webhook_router = APIRouter(prefix="/candidates", tags=["webhook"])


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

        existing = await TaskStore.get_by_candidate(candidate_id)
        if existing is not None:
            await AuditLog.append("task_generation_skipped", {
                "candidate_id": candidate_id,
                "existing_task_id": existing.id,
            })
            return f"task_already_exists:{existing.id}"

        output = await TaskDecomposerAgent.decompose(candidate_role=role, candidate_level=level)

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
def run_submission_evaluation(self: object, candidate_id: str, submission_url: str) -> str:  # noqa: ARG001
    """
    Async task: fetch latest SHA + source from GitHub, run sandbox + Evaluation Agent,
    walk FSM through UNDER_EVALUATION → FEEDBACK_SENT.
    Works for both first submissions (AWAITING_SUBMISSION) and resubmissions (AWAITING_RESUBMISSION).
    """
    async def _run() -> str:
        from app.agents.evaluation_agent import EvaluationAgent
        from app.models import EvaluationModel
        from app.services.candidate_store import CandidateStore
        from app.services.evaluation_store import EvaluationStore
        from app.services.github_service import GithubService
        from app.services.sandbox_runner import SandboxRunner
        from app.services.task_store import TaskStore

        candidate = await CandidateStore.get_by_id(candidate_id)
        if candidate is None:
            return f"candidate_not_found:{candidate_id}"

        task = await TaskStore.get_by_candidate(candidate_id)
        if task is None:
            await AuditLog.append("submission_task_no_task", {"candidate_id": candidate_id})
            return f"task_not_found:{candidate_id}"

        try:
            sha = await GithubService.fetch_latest_sha(submission_url)
            source_code = await GithubService.fetch_source_code(submission_url, sha)
        except Exception as e:
            await AuditLog.append("submission_github_fetch_failed", {
                "candidate_id": candidate_id,
                "submission_url": submission_url,
                "error": str(e),
            })
            return f"github_fetch_failed:{candidate_id}"

        fsm = FSMEngine()

        # Use the right predicate key for whichever state the candidate is in
        is_resubmission = candidate.state == CandidateState.AWAITING_RESUBMISSION
        sha_context = {"resubmission_sha": sha} if is_resubmission else {"submission_sha": sha}

        transitioned = await fsm.transition(
            candidate_id=candidate_id,
            target_state=CandidateState.UNDER_EVALUATION,
            context=sha_context,
            actor="submission_task",
        )
        if transitioned:
            await CandidateStore.update_state(candidate_id, CandidateState.UNDER_EVALUATION)

        round_number = await EvaluationStore.get_round_count(candidate_id) + 1
        held_out_tests = task.internal_spec.get("held_out_tests", [])

        sandbox_result = SandboxRunner.run(
            source_code=source_code,
            held_out_tests=held_out_tests,
        )

        await AuditLog.append("submission_sandbox_complete", {
            "candidate_id": candidate_id,
            "round": round_number,
            "is_resubmission": is_resubmission,
            "pass_rate": sandbox_result.pass_rate,
        })

        try:
            agent_output = await EvaluationAgent.evaluate(
                source_code=source_code,
                sandbox_result=sandbox_result,
                internal_spec=task.internal_spec,
                candidate_round=round_number,
            )
        except RuntimeError as e:
            await AuditLog.append("submission_evaluation_failed", {
                "candidate_id": candidate_id,
                "error": str(e),
            })
            return f"evaluation_failed:{candidate_id}"

        evaluation = EvaluationModel(
            candidate_id=candidate_id,
            round=round_number,
            submission_sha=sha,
            dimension_scores=agent_output.dimension_scores,
            composite=agent_output.composite,
            evidence={"evidence_summary": agent_output.evidence_summary},
            red_flags=agent_output.red_flags,
            feedback_draft=agent_output.candidate_feedback_draft,
        )
        evaluation_id = await EvaluationStore.add(evaluation)

        # UNDER_EVALUATION → FEEDBACK_SENT
        transitioned = await fsm.transition(
            candidate_id=candidate_id,
            target_state=CandidateState.FEEDBACK_SENT,
            context={"evaluation_record_id": evaluation_id},
            actor="submission_task",
        )
        if transitioned:
            await CandidateStore.update_state(candidate_id, CandidateState.FEEDBACK_SENT)

        await AuditLog.append("submission_evaluated_async", {
            "candidate_id": candidate_id,
            "evaluation_id": evaluation_id,
            "round": round_number,
            "is_resubmission": is_resubmission,
            "composite": agent_output.composite,
            "sha": sha,
        })
        return f"submission_evaluated:{evaluation_id}:round={round_number}"

    return asyncio.run(_run())


# Keep old name as alias so any already-queued tasks don't break
run_resubmission_evaluation = run_submission_evaluation


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)  # type: ignore[misc]
def renew_gmail_watch(self: object) -> str:  # noqa: ARG001
    """
    Periodic task: renew Gmail Pub/Sub watch before the 7-day expiry.
    Scheduled every 6 days via Celery beat.
    """
    async def _run() -> str:
        from app.config import GMAIL_PUBSUB_TOPIC
        if not GMAIL_PUBSUB_TOPIC:
            return "skipped:no_pubsub_topic"
        from app.services.gmail_service import GmailService
        svc = GmailService()
        result = await svc.register_watch(GMAIL_PUBSUB_TOPIC)
        await AuditLog.append("gmail_watch_renewed", {
            "topic": GMAIL_PUBSUB_TOPIC,
            "history_id": result.get("historyId"),
            "expiration": result.get("expiration"),
        })
        return f"watch_renewed:expiration={result.get('expiration')}"

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


class InviteRequest(BaseModel):
    to_email: str
    role: str = "Senior Software Engineer"
    personal_note: str = "Your background caught my attention — particularly your systems work."
    sender_name: str = "CureForge Team"


@router.post("/{candidate_id}/invite")
async def send_invite(candidate_id: str, payload: InviteRequest) -> dict:
    """
    Send initial outreach email to a candidate via the template responder.
    Always drafts for founder approval — never auto-sent.
    """
    from app.agents.template_responder import TemplateResponderAgent
    from app.services.approval_queue import ApprovalQueue, DraftEmail
    from app.services.candidate_store import CandidateStore

    candidate = await CandidateStore.get_by_id(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id!r} not found.")

    result = await TemplateResponderAgent.render(
        template_id="initial-outreach",
        candidate_context={
            "candidate_name": candidate.name,
            "sender_name": payload.sender_name,
        },
        extra_context={
            "role": payload.role,
            "personal_note": payload.personal_note,
        },
    )

    if result.constraint_check == "FAIL":
        raise HTTPException(status_code=422, detail="Template constraint violation.")

    draft = DraftEmail(
        candidate_id=candidate_id,
        template_id="initial-outreach",
        subject=result.subject,
        body=result.body,
        to_email=payload.to_email,
    )
    draft_id = await ApprovalQueue.add(draft)

    await AuditLog.append("invite_drafted", {
        "candidate_id": candidate_id,
        "role": payload.role,
        "draft_id": draft_id,
    })

    return {"status": "draft_queued", "draft_id": draft_id, "subject": result.subject}


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


@webhook_router.post("/webhook")
async def gmail_webhook(payload: WebhookPayload) -> dict:
    """Receive Gmail Pub/Sub push notifications — unprotected, called by Google."""
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


# ---------------------------------------------------------------------------
# /auth/google/callback — matches the redirect URI registered in Google Cloud Console
# ---------------------------------------------------------------------------

auth_google_router = APIRouter(prefix="/auth/google", tags=["oauth"])


@auth_google_router.get("/callback")
async def google_oauth_callback(code: str) -> dict:
    """
    Google redirects here after the user approves the OAuth consent screen.
    Mirrors /oauth/callback — same handler, different path to match the
    registered redirect URI in google_credentials.json.
    """
    from app.services.gmail_service import GmailService
    from fastapi.responses import HTMLResponse
    try:
        await GmailService.complete_oauth(code)
        return HTMLResponse(
            content="<html><body><h2>Gmail connected successfully.</h2>"
                    "<p>You can close this tab.</p></body></html>"
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
