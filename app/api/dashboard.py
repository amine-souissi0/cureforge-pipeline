from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.fsm import CandidateState
from app.schemas import AuditLog
from app.services.approval_queue import ApprovalQueue, DraftEmail
from app.services.evaluation_store import EvaluationStore
from app.services.candidate_store import CandidateStore

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class DraftOfferRequest(BaseModel):
    role: str
    compensation: str
    equity: str = ""
    benefits: str = ""
    to_email: str
    sender_name: str = "CureForge Team"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/pipeline")
async def pipeline_overview() -> Dict[str, Any]:
    """
    Pipeline-wide summary: candidate count by FSM state, and a snapshot
    of every candidate with their latest evaluation result.
    """
    candidates = CandidateStore.list_all()
    by_state = CandidateStore.count_by_state()

    rows = []
    for c in candidates:
        latest = EvaluationStore.get_latest_by_candidate(c.id)
        rows.append({
            "candidate_id": c.id,
            "name": c.name,
            "email": c.email,
            "state": c.state.value,
            "rounds_completed": EvaluationStore.get_round_count(c.id),
            "latest_composite": latest.composite if latest else None,
        })

    pending_drafts = len(ApprovalQueue.list_pending())

    return {
        "total_candidates": len(candidates),
        "by_state": by_state,
        "pending_drafts": pending_drafts,
        "candidates": rows,
    }


@router.get("/candidate/{candidate_id}")
async def candidate_detail(candidate_id: str) -> Dict[str, Any]:
    """
    Per-candidate view: evaluation history, pending drafts,
    and projected next state from the decision engine.
    """
    candidate = CandidateStore.get_by_id(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id!r} not found.")

    evaluations = EvaluationStore.list_by_candidate(candidate_id)
    pending_drafts = [
        {
            "draft_id": d.draft_id,
            "template_id": d.template_id,
            "subject": d.subject,
            "status": d.status,
        }
        for d in ApprovalQueue.list_pending()
        if d.candidate_id == candidate_id
    ]

    projected: Optional[str] = None
    if evaluations:
        from app.services.decision_engine import decide
        latest = evaluations[-1]
        decision = decide(
            composite=latest.composite,
            rounds_completed=len(evaluations),
        )
        projected = decision.next_state.value

    return {
        "candidate_id": candidate_id,
        "name": candidate.name,
        "email": candidate.email,
        "current_state": candidate.state.value,
        "rounds_completed": len(evaluations),
        "evaluations": [
            {
                "round": e.round,
                "composite": e.composite,
                "sha": e.submission_sha,
                "created_at": e.created_at.isoformat(),
            }
            for e in evaluations
        ],
        "pending_drafts": pending_drafts,
        "projected_next_state": projected,
    }


@router.get("/drafts")
async def pending_drafts() -> Dict[str, Any]:
    """
    Approval queue: all drafts awaiting founder review.
    """
    drafts = ApprovalQueue.list_pending()
    return {
        "pending_count": len(drafts),
        "drafts": [
            {
                "draft_id": d.draft_id,
                "candidate_id": d.candidate_id,
                "template_id": d.template_id,
                "subject": d.subject,
                "to_email": d.to_email,
                "created_at": d.created_at.isoformat(),
            }
            for d in drafts
        ],
    }


@router.post("/offer/{candidate_id}")
async def draft_offer(candidate_id: str, payload: DraftOfferRequest) -> Dict[str, Any]:
    """
    Initiate offer drafting for a HIRE_RECOMMENDED candidate.

    Calls the OfferDrafterAgent (Claude Sonnet), renders the offer-cover
    template, and queues the result as a draft for founder approval.
    Only valid when the candidate's latest evaluation composite >= HIRE_THRESHOLD.
    """
    from app.agents.offer_drafter import OfferDrafterAgent
    from app.agents.template_responder import TemplateResponderAgent

    candidate = CandidateStore.get_by_id(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id!r} not found.")

    latest_eval = EvaluationStore.get_latest_by_candidate(candidate_id)
    if latest_eval is None:
        raise HTTPException(
            status_code=400,
            detail="No evaluations found — candidate has not been evaluated yet.",
        )

    from config.rubric import HIRE_THRESHOLD
    if latest_eval.composite < HIRE_THRESHOLD:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Composite {latest_eval.composite:.2f} is below hire threshold {HIRE_THRESHOLD}. "
                "Offer drafting requires a hire-bar evaluation."
            ),
        )

    try:
        offer_output = await OfferDrafterAgent.draft(
            candidate_name=candidate.name,
            role=payload.role,
            compensation=payload.compensation,
            equity=payload.equity,
            benefits=payload.benefits,
            sender_name=payload.sender_name,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    if offer_output.constraint_check == "FAIL":
        raise HTTPException(
            status_code=422,
            detail="Offer drafter returned constraint failure — review required.",
        )

    template_output = await TemplateResponderAgent.render(
        template_id="offer-cover",
        candidate_context={
            "candidate_name": candidate.name,
            "sender_name": payload.sender_name,
        },
        extra_context={"offer_details": offer_output.offer_details},
    )

    draft = DraftEmail(
        candidate_id=candidate_id,
        template_id="offer-cover",
        subject=template_output.subject,
        body=template_output.body,
        to_email=payload.to_email,
    )
    draft_id = await ApprovalQueue.add(draft)

    await AuditLog.append("offer_draft_created", {
        "candidate_id": candidate_id,
        "role": payload.role,
        "draft_id": draft_id,
        "composite": latest_eval.composite,
    })

    return {
        "candidate_id": candidate_id,
        "draft_id": draft_id,
        "role": offer_output.role,
        "subject": template_output.subject,
        "status": "draft_queued_for_approval",
    }
