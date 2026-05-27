import csv
import io
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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
    candidates = await CandidateStore.list_all()
    by_state = await CandidateStore.count_by_state()

    rows = []
    for c in candidates:
        latest = await EvaluationStore.get_latest_by_candidate(c.id)
        rows.append({
            "candidate_id": c.id,
            "name": c.name,
            "email": c.email,
            "state": c.state.value,
            "rounds_completed": await EvaluationStore.get_round_count(c.id),
            "latest_composite": latest.composite if latest else None,
            # §10 evaluation table — per-dimension breakdown
            "dimension_scores": latest.dimension_scores if latest else None,
        })

    pending_drafts = len(await ApprovalQueue.list_pending())

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
    candidate = await CandidateStore.get_by_id(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id!r} not found.")

    evaluations = await EvaluationStore.list_by_candidate(candidate_id)
    pending_drafts = [
        {
            "draft_id": d.draft_id,
            "template_id": d.template_id,
            "subject": d.subject,
            "status": d.status,
        }
        for d in await ApprovalQueue.list_pending()
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
    drafts = await ApprovalQueue.list_pending()
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

    candidate = await CandidateStore.get_by_id(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id!r} not found.")

    latest_eval = await EvaluationStore.get_latest_by_candidate(candidate_id)
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


@router.get("/candidate/{candidate_id}/dossier")
async def candidate_dossier(candidate_id: str) -> Dict[str, Any]:
    """
    §9 — Full hire dossier: all evaluation rounds, dimension scores, evidence,
    red flags, and message transcript. Assembled when HIRE_RECOMMENDED fires;
    also available on demand here.
    """
    from app.services.dossier_service import assemble_dossier
    candidate = await CandidateStore.get_by_id(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id!r} not found.")
    return await assemble_dossier(candidate_id)


@router.get("/candidate/{candidate_id}/transcript")
async def candidate_transcript(candidate_id: str) -> Dict[str, Any]:
    """§11 — Full inbound + outbound message history for a candidate."""
    from app.services.message_store import MessageStore
    candidate = await CandidateStore.get_by_id(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id!r} not found.")
    messages = await MessageStore.list_by_candidate(candidate_id)
    return {
        "candidate_id": candidate_id,
        "name": candidate.name,
        "total_messages": len(messages),
        "messages": [
            {
                "direction": m.direction,
                "template_id": m.template_id,
                "subject": m.subject,
                "body": m.body,
                "sent_by_agent": m.sent_by_agent,
                "approved_by": m.approved_by,
                "gmail_id": m.gmail_id,
                "ts": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }


@router.get("/export.csv")
async def export_evaluation_table() -> StreamingResponse:
    """
    §10 — Export evaluation table as CSV.
    One row per candidate: composite, per-dimension scores, rounds, state.
    """
    from config.rubric import DIMENSIONS
    candidates = await CandidateStore.list_all()

    buf = io.StringIO()
    dim_ids = list(DIMENSIONS.keys())
    fieldnames = ["candidate_id", "name", "email", "state", "rounds", "composite"] + dim_ids
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()

    for c in candidates:
        latest = await EvaluationStore.get_latest_by_candidate(c.id)
        rounds = await EvaluationStore.get_round_count(c.id)
        dim_scores = latest.dimension_scores if latest else {}
        row: Dict[str, Any] = {
            "candidate_id": c.id,
            "name": c.name,
            "email": c.email,
            "state": c.state.value,
            "rounds": rounds,
            "composite": latest.composite if latest else "",
        }
        for dim_id in dim_ids:
            row[dim_id] = dim_scores.get(dim_id, "")
        writer.writerow(row)

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=evaluation_table.csv"},
    )
