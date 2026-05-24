from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas import AuditLog
from app.services.approval_queue import ApprovalQueue, DraftEmail
from app.services.send_policy import SendMode, get_send_mode
from app.templates import TemplateRegistry

router = APIRouter(prefix="/templates", tags=["templates"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SendRequest(BaseModel):
    candidate_id: str
    template_id: str
    to_email: str
    candidate_context: Dict[str, str]
    extra_context: Optional[Dict[str, str]] = None


class DraftDecisionRequest(BaseModel):
    reviewer: str = "founder"


class DraftResponse(BaseModel):
    draft_id: str
    candidate_id: str
    template_id: str
    subject: str
    body: str
    to_email: str
    status: str
    created_at: str
    reviewed_by: Optional[str] = None


def _draft_to_response(draft: DraftEmail) -> DraftResponse:
    return DraftResponse(
        draft_id=draft.draft_id,
        candidate_id=draft.candidate_id,
        template_id=draft.template_id,
        subject=draft.subject,
        body=draft.body,
        to_email=draft.to_email,
        status=draft.status,
        created_at=draft.created_at.isoformat(),
        reviewed_by=draft.reviewed_by,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_templates() -> Dict[str, List[str]]:
    """List all available template IDs."""
    return {"templates": TemplateRegistry.list_templates()}


@router.post("/send")
async def send_template(payload: SendRequest) -> dict:
    """
    Trigger the Template Responder agent for a candidate.

    Depending on the send policy:
    - AUTO templates are sent immediately via Gmail.
    - DRAFT templates are queued for founder approval.
    """
    from app.agents.template_responder import TemplateResponderAgent
    from app.services.gmail_service import GmailService

    try:
        result = await TemplateResponderAgent.render(
            template_id=payload.template_id,
            candidate_context=payload.candidate_context,
            extra_context=payload.extra_context,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    if result.constraint_check == "FAIL":
        raise HTTPException(
            status_code=422,
            detail="Template Responder flagged a constraint violation. Routed to human review.",
        )

    mode = get_send_mode(payload.candidate_id, payload.template_id)

    if mode == SendMode.AUTO:
        svc = GmailService()
        gmail_id = await svc.send_email(
            to=payload.to_email,
            subject=result.subject,
            body=result.body,
        )
        await AuditLog.append("template_auto_sent", {
            "candidate_id": payload.candidate_id,
            "template_id": payload.template_id,
            "gmail_id": gmail_id,
        })
        return {"status": "sent", "gmail_id": gmail_id}

    # DRAFT — queue for approval
    draft = DraftEmail(
        candidate_id=payload.candidate_id,
        template_id=payload.template_id,
        subject=result.subject,
        body=result.body,
        to_email=payload.to_email,
    )
    draft_id = await ApprovalQueue.add(draft)
    return {"status": "draft", "draft_id": draft_id}


@router.get("/drafts")
async def list_drafts() -> Dict[str, list]:
    """List all pending drafts awaiting founder approval."""
    pending = ApprovalQueue.list_pending()
    return {"drafts": [_draft_to_response(d).model_dump() for d in pending]}


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(draft_id: str, payload: DraftDecisionRequest) -> dict:
    """Approve a draft and send it via Gmail."""
    from app.services.gmail_service import GmailService

    draft = await ApprovalQueue.approve(draft_id, payload.reviewer)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id!r} not found.")

    if draft.status != "approved":
        raise HTTPException(
            status_code=409,
            detail=f"Draft is not pending (status: {draft.status}).",
        )

    svc = GmailService()
    gmail_id = await svc.send_email(
        to=draft.to_email,
        subject=draft.subject,
        body=draft.body,
    )
    await ApprovalQueue.mark_sent(draft_id)

    await AuditLog.append("draft_approved_and_sent", {
        "draft_id": draft_id,
        "reviewer": payload.reviewer,
        "gmail_id": gmail_id,
        "candidate_id": draft.candidate_id,
    })

    return {"status": "sent", "draft_id": draft_id, "gmail_id": gmail_id}


@router.post("/drafts/{draft_id}/reject")
async def reject_draft(draft_id: str, payload: DraftDecisionRequest) -> dict:
    """Reject a draft — it will not be sent."""
    draft = await ApprovalQueue.reject(draft_id, payload.reviewer)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id!r} not found.")

    return {"status": "rejected", "draft_id": draft_id}
