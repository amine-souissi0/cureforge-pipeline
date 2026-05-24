"""
Webhook processor: turns a parsed inbound Gmail message into pipeline actions.

Separated from the Celery task so the logic is unit-testable without a broker.
"""
from typing import Optional

from app.fsm import CandidateState, FSMEngine
from app.models import CandidateModel
from app.schemas import AuditLog, Message, ReplyClassifierOutput


async def process_inbound_message(message: Message) -> str:
    """
    Full pipeline for one inbound Gmail message:
    1. Look up candidate by sender email — skip if unknown
    2. Classify intent with ReplyClassifierAgent
    3. Execute routing action
    4. Audit every step

    Returns a short result string for the Celery task log.
    """
    from app.agents.reply_classifier import ReplyClassifierAgent, route_classified_email
    from app.services.candidate_store import CandidateStore

    candidate = await CandidateStore.get_by_email(message.sender_email)
    if candidate is None:
        await AuditLog.append("webhook_unknown_sender", {
            "sender_email": message.sender_email,
            "gmail_message_id": message.message_id,
        })
        return f"unknown_sender:{message.sender_email}"

    await AuditLog.append("webhook_candidate_matched", {
        "candidate_id": candidate.id,
        "sender_email": message.sender_email,
        "state": candidate.state.value,
        "gmail_message_id": message.message_id,
    })

    output = await ReplyClassifierAgent.classify_email(
        email_body=message.body,
        candidate_context=candidate.name,
    )

    routing = route_classified_email(output, candidate.id)

    await AuditLog.append("email_classified", {
        "candidate_id": candidate.id,
        "intent": output.intent,
        "confidence": output.confidence,
        "routing": routing,
        "summary": output.summary,
        "gmail_message_id": message.message_id,
    })

    await _execute_routing(routing, candidate, message, output)
    return f"{candidate.id}:{output.intent}→{routing}"


async def _execute_routing(
    routing: str,
    candidate: CandidateModel,
    message: Message,
    output: ReplyClassifierOutput,
) -> None:
    if routing == "fsm_withdrawn":
        await _handle_decline(candidate)
        return

    if routing.startswith("submission_intake:"):
        submission_url = routing.split(":", 1)[1]
        await _handle_submission(candidate, message, submission_url)
        return

    if routing.startswith("template_responder:"):
        intent = routing.split(":", 1)[1]
        await _handle_template_response(candidate, message, intent)
        return

    # human_review or human_review_no_url — flag for founder, no automated action
    await AuditLog.append("human_review_flagged", {
        "candidate_id": candidate.id,
        "intent": output.intent,
        "confidence": output.confidence,
        "summary": output.summary,
        "gmail_message_id": message.message_id,
        "routing": routing,
    })


async def _handle_decline(candidate: CandidateModel) -> None:
    from app.services.candidate_store import CandidateStore

    fsm = FSMEngine()
    transitioned = await fsm.transition(
        candidate_id=candidate.id,
        target_state=CandidateState.WITHDRAWN,
        context={"intent": "DECLINE"},
        actor="webhook_processor",
    )
    if transitioned:
        await CandidateStore.update_state(candidate.id, CandidateState.WITHDRAWN)

    await AuditLog.append("candidate_withdrawn", {
        "candidate_id": candidate.id,
        "reason": "DECLINE_intent",
        "fsm_transitioned": transitioned,
    })


async def _handle_submission(
    candidate: CandidateModel,
    message: Message,
    submission_url: str,
) -> None:
    from app.services.task_store import TaskStore

    task = await TaskStore.get_by_candidate(candidate.id)
    if task:
        await TaskStore.update_repo_url(task.id, submission_url)

    await AuditLog.append("submission_received", {
        "candidate_id": candidate.id,
        "submission_url": submission_url,
        "task_id": task.id if task else None,
        "gmail_message_id": message.message_id,
    })

    # Acknowledge receipt — founder will review and trigger evaluation
    await _queue_template(
        candidate=candidate,
        template_id="acknowledgment",
        original_subject=message.subject,
    )


async def _handle_template_response(
    candidate: CandidateModel,
    message: Message,
    intent: str,
) -> None:
    template_id = _intent_to_template(intent)
    if template_id is None:
        await AuditLog.append("no_template_for_intent", {
            "candidate_id": candidate.id,
            "intent": intent,
        })
        return

    await _queue_template(
        candidate=candidate,
        template_id=template_id,
        original_subject=message.subject,
    )


def _intent_to_template(intent: str) -> Optional[str]:
    return {
        "INTERESTED": "acknowledgment",
        "SCHEDULING": "acknowledgment",
        "QUESTION": "answer-common-question",
    }.get(intent)


async def _queue_template(
    candidate: CandidateModel,
    template_id: str,
    original_subject: str = "",
) -> None:
    from app.agents.template_responder import TemplateResponderAgent
    from app.services.approval_queue import ApprovalQueue, DraftEmail
    from app.services.send_policy import SendMode, get_send_mode

    try:
        result = await TemplateResponderAgent.render(
            template_id=template_id,
            candidate_context={
                "candidate_name": candidate.name,
                "sender_name": "CureForge Team",
                "original_subject": original_subject,
            },
        )
    except Exception as e:
        await AuditLog.append("template_render_failed", {
            "candidate_id": candidate.id,
            "template_id": template_id,
            "error": str(e),
        })
        return

    send_mode = get_send_mode(candidate.id, template_id)

    if send_mode == SendMode.AUTO:
        from app.services.gmail_service import GmailService
        svc = GmailService()
        try:
            gmail_id = await svc.send_email(
                to=candidate.email,
                subject=result.subject,
                body=result.body,
            )
            await AuditLog.append("template_auto_sent", {
                "candidate_id": candidate.id,
                "template_id": template_id,
                "gmail_id": gmail_id,
            })
        except Exception as e:
            await AuditLog.append("template_send_failed", {
                "candidate_id": candidate.id,
                "template_id": template_id,
                "error": str(e),
            })
    else:
        draft = DraftEmail(
            candidate_id=candidate.id,
            template_id=template_id,
            subject=result.subject,
            body=result.body,
            to_email=candidate.email,
        )
        draft_id = await ApprovalQueue.add(draft)
        await AuditLog.append("template_draft_queued", {
            "candidate_id": candidate.id,
            "template_id": template_id,
            "draft_id": draft_id,
        })
