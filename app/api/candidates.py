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


def _rewrite_function_name(
    held_out_tests: list,
    old_name: str,
    new_name: str,
) -> list:
    """Replace occurrences of old_name( with new_name( in each test's input expression."""
    updated = []
    for test in held_out_tests:
        t = dict(test)
        if isinstance(t.get("input"), str):
            t["input"] = t["input"].replace(f"{old_name}(", f"{new_name}(")
        updated.append(t)
    return updated


async def fsm_advance_to_awaiting(candidate_id: str, task_id: str) -> None:
    """ENGAGED → TASK_ASSIGNED → AWAITING_SUBMISSION after brief auto-sent."""
    from app.services.candidate_store import CandidateStore
    fsm = FSMEngine()
    transitioned = await fsm.transition(
        candidate_id=candidate_id,
        target_state=CandidateState.TASK_ASSIGNED,
        context={"intent": "INTERESTED", "task_id": task_id},
        actor="task_celery",
    )
    if transitioned:
        await CandidateStore.update_state(candidate_id, CandidateState.TASK_ASSIGNED)
    fsm2 = FSMEngine()
    transitioned2 = await fsm2.transition(
        candidate_id=candidate_id,
        target_state=CandidateState.AWAITING_SUBMISSION,
        context={"task_brief_sent": True},
        actor="task_celery",
    )
    if transitioned2:
        await CandidateStore.update_state(candidate_id, CandidateState.AWAITING_SUBMISSION)


async def dispatch_outcome_email(
    candidate_id: str,
    composite: float,
    round_number: int,
    feedback_text: str,
) -> None:
    """Fire outcome FSM transition and send the appropriate email to the candidate."""
    from app.services.approval_queue import ApprovalQueue, DraftEmail
    from app.services.candidate_store import CandidateStore
    from app.services.gmail_service import GmailService
    from app.services.send_policy import SendMode, get_send_mode
    from app.templates import TemplateRegistry

    candidate = await CandidateStore.get_by_id(candidate_id)
    if candidate is None:
        return

    fsm = FSMEngine()
    next_state: Optional[CandidateState] = None

    # Try outcome transitions in priority order
    for target, ctx in [
        (CandidateState.HIRE_RECOMMENDED, {"composite": composite, "mode": "recommend"}),
        (CandidateState.WARM_HOLD, {"composite": composite, "rounds": round_number}),
        (CandidateState.AWAITING_RESUBMISSION, {"composite": composite}),
    ]:
        if await fsm.transition(candidate_id, target, ctx, "outcome_engine"):
            await CandidateStore.update_state(candidate_id, target)
            next_state = target
            break

    # composite < 7 on round 1: no FSM rule covers it — give one resubmission chance
    if next_state is None and composite < 7.0 and round_number < 2:
        await fsm.force_set_state(candidate_id, CandidateState.AWAITING_RESUBMISSION,
                                  "outcome_engine", f"round={round_number} composite={composite}")
        await CandidateStore.update_state(candidate_id, CandidateState.AWAITING_RESUBMISSION)
        next_state = CandidateState.AWAITING_RESUBMISSION

    if next_state == CandidateState.HIRE_RECOMMENDED:
        # Don't email candidate yet — founder must confirm hire before offer
        await AuditLog.append("hire_recommended_pending_founder", {
            "candidate_id": candidate_id, "composite": composite,
        })
        return

    if next_state == CandidateState.WARM_HOLD:
        template_id = "warm-hold"
        fields = {"candidate_name": candidate.name, "sender_name": "CureForge Team"}
    else:
        template_id = "feedback-delivery"
        fields = {
            "candidate_name": candidate.name,
            "feedback": feedback_text,
            "upgrade_ask": "Please address the gaps above and resubmit your solution.",
            "sender_name": "CureForge Team",
        }

    subject, body = TemplateRegistry.render(template_id, fields)
    send_mode = get_send_mode(candidate_id, template_id)

    if send_mode == SendMode.AUTO:
        svc = GmailService()
        gmail_id = await svc.send_email(to=candidate.email, subject=subject, body=body)
        await AuditLog.append("outcome_email_auto_sent", {
            "candidate_id": candidate_id, "template_id": template_id,
            "next_state": next_state.value if next_state else None, "gmail_id": gmail_id,
        })
    else:
        draft = DraftEmail(candidate_id=candidate_id, template_id=template_id,
                           subject=subject, body=body, to_email=candidate.email)
        await ApprovalQueue.add(draft)
        await AuditLog.append("outcome_email_draft_queued", {
            "candidate_id": candidate_id, "template_id": template_id,
            "next_state": next_state.value if next_state else None,
        })


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class IntakeRequest(BaseModel):
    name: str
    email: str
    github_handle: Optional[str] = None
    source: str = "founder_added"
    role: str = "Software Engineer"
    level: str = "senior"
    personal_note: str = "Your background caught our attention — we think you'd be a strong fit."


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
def generate_task_for_candidate(self: object, candidate_id: str, role: str = "software engineer", level: str = "senior", corpus_pattern: str = "") -> str:  # noqa: ARG001
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

        output = await TaskDecomposerAgent.decompose(
            candidate_role=role,
            candidate_level=level,
            background_notes=candidate.background_notes or "",
            preferred_pattern_id=corpus_pattern or None,
        )

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

        # Provision GitHub repo so the URL is in the brief
        from app.services.github_service import GithubService
        from app.schemas import InternalTaskSpec
        repo_url = ""
        try:
            internal_spec = InternalTaskSpec(**task.internal_spec) if task.internal_spec else InternalTaskSpec(
                expected_behavior="See task spec.", held_out_tests=[], failure_modes=[],
            )
            repo_url = await GithubService().provision_repo(
                candidate_id=candidate_id,
                task_id=task_id,
                internal_spec=internal_spec,
            )
            await TaskStore.update_repo_url(task_id, repo_url)
        except Exception as exc:
            await AuditLog.append("github_provision_failed", {"candidate_id": candidate_id, "error": str(exc)})

        # Send (or draft) the task brief immediately after generation
        from app.services.approval_queue import ApprovalQueue, DraftEmail
        from app.services.gmail_service import GmailService
        from app.services.send_policy import SendMode, get_send_mode
        from app.templates import TemplateRegistry

        subject, body = TemplateRegistry.render("task-assignment-cover", {
            "candidate_name": candidate.name,
            "task_brief": output.candidate_brief,
            "sender_name": "CureForge Team",
        })
        send_mode = get_send_mode(candidate_id, "task-assignment-cover")

        if send_mode == SendMode.AUTO:
            svc = GmailService()
            gmail_id = await svc.send_email(to=candidate.email, subject=subject, body=body)
            await AuditLog.append("task_brief_auto_sent", {
                "candidate_id": candidate_id, "task_id": task_id, "gmail_id": gmail_id,
            })
            # Advance FSM: ENGAGED → TASK_ASSIGNED → AWAITING_SUBMISSION
            await fsm_advance_to_awaiting(candidate_id, task_id)
        else:
            draft = DraftEmail(
                candidate_id=candidate_id,
                template_id="task-assignment-cover",
                subject=subject,
                body=body,
                to_email=candidate.email,
            )
            await ApprovalQueue.add(draft)
            await AuditLog.append("task_brief_draft_queued", {"candidate_id": candidate_id, "task_id": task_id})
            # ENGAGED → TASK_ASSIGNED only (brief not yet sent, so not AWAITING_SUBMISSION)
            fsm = FSMEngine()
            transitioned = await fsm.transition(
                candidate_id=candidate_id,
                target_state=CandidateState.TASK_ASSIGNED,
                context={"intent": "INTERESTED", "task_id": task_id},
                actor="task_celery",
            )
            if transitioned:
                await CandidateStore.update_state(candidate_id, CandidateState.TASK_ASSIGNED)

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
            file_tree = await GithubService.fetch_file_tree(submission_url, sha)
            readme = await GithubService.fetch_readme(submission_url)
        except Exception as e:
            await AuditLog.append("submission_github_fetch_failed", {
                "candidate_id": candidate_id,
                "submission_url": submission_url,
                "error": str(e),
            })
            return f"github_fetch_failed:{candidate_id}"

        # Use the RepoExecutionAgent to find the entry file + function name
        from app.agents.repo_execution_agent import RepoExecutionAgent

        expected_fn = task.internal_spec.get("function_name", "")
        expected_behavior = task.internal_spec.get("expected_behavior", "")
        exec_plan = await RepoExecutionAgent.analyze(
            repo_url=submission_url,
            file_tree=file_tree,
            readme_content=readme,
            expected_function_name=expected_fn,
            expected_behavior=expected_behavior,
        )

        # Fetch the identified entry file; fall back to all Python files if not found
        try:
            source_code = await GithubService.fetch_file_content(
                submission_url, exec_plan.entry_file, sha
            )
        except Exception:
            await AuditLog.append("entry_file_fetch_fallback", {
                "candidate_id": candidate_id,
                "entry_file": exec_plan.entry_file,
            })
            source_code = await GithubService.fetch_source_code(submission_url, sha)

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

        # Rewrite test inputs if the candidate used a different function name
        held_out_tests = task.internal_spec.get("held_out_tests", [])
        if exec_plan.function_name and exec_plan.function_name != expected_fn and expected_fn:
            held_out_tests = _rewrite_function_name(
                held_out_tests, expected_fn, exec_plan.function_name
            )

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

        # Feedback loop: send feedback draft, run decision engine, advance FSM
        from app.services.feedback_controller import run_feedback_loop
        await run_feedback_loop(
            candidate_id=candidate_id,
            evaluation_id=evaluation_id,
            to_email=candidate.email,
            mode="recommend",
        )

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
        # Keep Redis historyId in sync so the poll task doesn't reprocess old messages
        try:
            import os, redis as redis_lib
            r = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
            r.set("gmail:last_history_id", result["historyId"])
        except Exception:
            pass
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
        import os
        import redis as redis_lib
        svc = GmailService()
        messages, latest_hid = await svc.list_new_messages(history_id)

        r = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))

        # Persist latest historyId so the poll task doesn't reprocess these messages
        if latest_hid:
            try:
                r.set("gmail:last_history_id", latest_hid)
            except Exception:
                pass

        if not messages:
            await AuditLog.append("process_email_task_no_messages", {
                "history_id": history_id,
            })
            return f"no_new_messages:history_id={history_id}"

        results = []
        for message in messages:
            # Idempotency: skip Gmail message IDs already processed by any path
            redis_key = f"gmail:processed:{message.message_id}"
            if r.exists(redis_key):
                results.append(f"already_processed:{message.message_id}")
                continue
            r.set(redis_key, "1", ex=7 * 24 * 3600)
            result = await process_inbound_message(message)
            results.append(result)

        return "; ".join(results)

    return asyncio.run(_run())


@celery_app.task(bind=True, max_retries=1)  # type: ignore[misc]
def poll_gmail_inbox(self: object) -> str:  # noqa: ARG001
    """
    Beat task: poll Gmail every 2 minutes for messages missed by Pub/Sub webhooks.
    Reads the last processed historyId from Redis; falls back to registering a fresh watch.
    """
    import os
    import redis as redis_lib

    async def _run() -> str:
        from app.config import GMAIL_PUBSUB_TOPIC
        from app.services.gmail_service import GmailService
        from app.services.webhook_processor import process_inbound_message

        r = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        raw = r.get("gmail:last_history_id")

        svc = GmailService()

        if not raw:
            # First run — initialize from watch registration
            if GMAIL_PUBSUB_TOPIC:
                result = await svc.register_watch(GMAIL_PUBSUB_TOPIC)
                r.set("gmail:last_history_id", result["historyId"])
            return "initialized"

        last_hid = raw.decode()
        messages, latest_hid = await svc.list_new_messages(last_hid)

        if latest_hid:
            r.set("gmail:last_history_id", latest_hid)

        if not messages:
            return f"no_new_messages:since={last_hid}"

        results = []
        for message in messages:
            # Idempotency: skip Gmail message IDs already processed
            redis_key = f"gmail:processed:{message.message_id}"
            if r.exists(redis_key):
                results.append(f"already_processed:{message.message_id}")
                continue
            r.set(redis_key, "1", ex=7 * 24 * 3600)  # expire after 7 days
            result = await process_inbound_message(message)
            results.append(result)

        await AuditLog.append("poll_gmail_inbox_processed", {
            "history_id": last_hid,
            "latest_history_id": latest_hid,
            "count": len(messages),
        })
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
            role=payload.role,
            level=payload.level,
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

    # Auto-queue outreach invite draft for founder approval
    if transitioned:
        from app.agents.template_responder import TemplateResponderAgent
        from app.services.approval_queue import ApprovalQueue, DraftEmail
        try:
            result = await TemplateResponderAgent.render(
                template_id="initial-outreach",
                candidate_context={
                    "candidate_name": candidate.name,
                    "role": payload.role,
                    "personal_note": payload.personal_note,
                    "sender_name": "CureForge Team",
                },
            )
            draft = DraftEmail(
                candidate_id=candidate.id,
                template_id="initial-outreach",
                subject=result.subject,
                body=result.body,
                to_email=candidate.email,
            )
            await ApprovalQueue.add(draft)
            await AuditLog.append("outreach_draft_queued", {"candidate_id": candidate.id})
        except Exception as exc:
            await AuditLog.append("outreach_draft_failed", {"candidate_id": candidate.id, "error": str(exc)})

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
    subject: str = "Re: Engineering Role"


@router.post("/simulate")
async def simulate_inbound(payload: ClassifyRequest) -> dict:
    """
    Full pipeline simulation: classify + route + execute actions.
    Use this to test the complete flow (background gathering, task generation, etc.)
    """
    from app.schemas import Message
    from app.services.webhook_processor import process_inbound_message

    ts = int(__import__('time').time())
    sim_id = f"sim-{ts}"
    message = Message(
        id=sim_id,
        message_id=sim_id,
        sender_email=payload.sender_email,
        sender_name=payload.sender_email.split("@")[0],
        subject=payload.subject,
        body=payload.body,
    )
    result = await process_inbound_message(message)
    return {"result": result}


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
        candidate_state=candidate.state.value if candidate else "",
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
