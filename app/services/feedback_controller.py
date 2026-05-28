from dataclasses import dataclass
from typing import Optional

from app.fsm import CandidateState, FSMEngine
from app.schemas import AuditLog
from app.services.decision_engine import Decision, decide
from app.services.evaluation_store import EvaluationStore


@dataclass
class FeedbackResult:
    candidate_id: str
    evaluation_id: str
    composite: float
    round_number: int
    decision: Decision
    feedback_draft_id: Optional[str]  # approval queue draft_id if DRAFT mode
    fsm_transitioned: bool


async def run_feedback_loop(
    candidate_id: str,
    evaluation_id: str,
    to_email: str,
    sender_name: str = "CureForge Team",
    mode: str = "recommend",
) -> FeedbackResult:
    """
    Full post-evaluation feedback loop:
    1. Load evaluation record
    2. Send feedback-delivery email (draft or auto based on send policy)
    3. Run decision engine
    4. Execute FSM transition
    5. If WARM_HOLD: send warm-hold template
    6. Audit every step

    This is the single entrypoint for all post-evaluation routing.
    """
    from app.agents.template_responder import TemplateResponderAgent
    from app.services.approval_queue import ApprovalQueue, DraftEmail
    from app.services.send_policy import SendMode, get_send_mode

    evaluation = await EvaluationStore.get_by_id(evaluation_id)
    if evaluation is None:
        raise ValueError(f"Evaluation {evaluation_id!r} not found.")

    rounds = await EvaluationStore.get_round_count(candidate_id)

    # Collect full composite history for trajectory analysis (§9)
    all_evals = await EvaluationStore.list_by_candidate(candidate_id)
    prior_composites = [e.composite for e in all_evals]

    from app.services.candidate_store import CandidateStore
    candidate = await CandidateStore.get_by_id(candidate_id)
    candidate_name = candidate.name if candidate else candidate_id

    await AuditLog.append("feedback_loop_started", {
        "candidate_id": candidate_id,
        "evaluation_id": evaluation_id,
        "composite": evaluation.composite,
        "round": evaluation.round,
    })

    # --- Step 1: Render and queue/send feedback email ---
    feedback_body, upgrade_ask = _split_feedback(evaluation.feedback_draft)
    feedback_result = await TemplateResponderAgent.render(
        template_id="feedback-delivery",
        candidate_context={
            "candidate_name": candidate_name,
            "sender_name": sender_name,
        },
        extra_context={
            "feedback": feedback_body,
            "upgrade_ask": upgrade_ask,
        },
    )

    draft_id: Optional[str] = None
    send_mode = get_send_mode(candidate_id, "feedback-delivery")

    if send_mode == SendMode.AUTO:
        from app.services.gmail_service import GmailService
        svc = GmailService()
        gmail_id = await svc.send_email(
            to=to_email,
            subject=feedback_result.subject,
            body=feedback_result.body,
        )
        await AuditLog.append("feedback_email_sent", {
            "candidate_id": candidate_id,
            "gmail_id": gmail_id,
        })
    else:
        draft = DraftEmail(
            candidate_id=candidate_id,
            template_id="feedback-delivery",
            subject=feedback_result.subject,
            body=feedback_result.body,
            to_email=to_email,
        )
        draft_id = await ApprovalQueue.add(draft)
        await AuditLog.append("feedback_draft_queued", {
            "candidate_id": candidate_id,
            "draft_id": draft_id,
        })

    # --- Step 2: Decision engine (trajectory-aware per §9) ---
    decision = decide(
        composite=evaluation.composite,
        rounds_completed=rounds,
        mode=mode,
        prior_composites=prior_composites,
    )

    await AuditLog.append("decision_made", {
        "candidate_id": candidate_id,
        "next_state": decision.next_state.value,
        "reasoning": decision.reasoning,
        "requires_founder_approval": decision.requires_founder_approval,
    })

    # --- Step 3: FSM transition ---
    fsm = FSMEngine()
    transitioned = await fsm.transition(
        candidate_id=candidate_id,
        target_state=decision.next_state,
        context=decision.fsm_context,
        actor="feedback_controller",
    )

    # --- Step 4a: Assemble dossier when hire recommended (§9) ---
    if decision.next_state == CandidateState.HIRE_RECOMMENDED and transitioned:
        from app.services.dossier_service import assemble_dossier
        await assemble_dossier(candidate_id)

    # --- Step 4b: Warm-hold email ---
    if decision.next_state == CandidateState.WARM_HOLD and transitioned:
        warm_hold = await TemplateResponderAgent.render(
            template_id="warm-hold",
            candidate_context={
                "candidate_name": candidate_name,
                "sender_name": sender_name,
            },
        )
        wh_draft = DraftEmail(
            candidate_id=candidate_id,
            template_id="warm-hold",
            subject=warm_hold.subject,
            body=warm_hold.body,
            to_email=to_email,
        )
        wh_draft_id = await ApprovalQueue.add(wh_draft)
        await AuditLog.append("warm_hold_draft_queued", {
            "candidate_id": candidate_id,
            "draft_id": wh_draft_id,
        })

    return FeedbackResult(
        candidate_id=candidate_id,
        evaluation_id=evaluation_id,
        composite=evaluation.composite,
        round_number=evaluation.round,
        decision=decision,
        feedback_draft_id=draft_id,
        fsm_transitioned=transitioned,
    )


def _split_feedback(feedback_draft: str) -> tuple[str, str]:
    """
    Split feedback into (body, upgrade_ask).
    Looks for an 'Upgrade your delivery' sentence; if found, uses it as the
    upgrade_ask and strips it from the body to avoid duplication.
    """
    lines = [l.strip() for l in feedback_draft.strip().splitlines() if l.strip()]
    upgrade_lines = [l for l in lines if l.lower().startswith("upgrade your delivery")]
    body_lines = [l for l in lines if not l.lower().startswith("upgrade your delivery")]

    body = " ".join(body_lines).strip()
    upgrade_ask = upgrade_lines[0] if upgrade_lines else ""
    return body, upgrade_ask
