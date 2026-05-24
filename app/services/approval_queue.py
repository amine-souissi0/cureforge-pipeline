import uuid
from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas import AuditLog


class DraftEmail(BaseModel):
    draft_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_id: str
    template_id: str
    subject: str
    body: str
    to_email: str
    status: Literal["pending", "approved", "rejected", "sent"] = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None


# In-memory store. Replace with Redis or DB-backed store in production.
_drafts: Dict[str, DraftEmail] = {}


class ApprovalQueue:
    @staticmethod
    async def add(draft: DraftEmail) -> str:
        _drafts[draft.draft_id] = draft
        await AuditLog.append("draft_created", {
            "draft_id": draft.draft_id,
            "candidate_id": draft.candidate_id,
            "template_id": draft.template_id,
        })
        return draft.draft_id

    @staticmethod
    def get(draft_id: str) -> Optional[DraftEmail]:
        return _drafts.get(draft_id)

    @staticmethod
    def list_pending() -> List[DraftEmail]:
        return [d for d in _drafts.values() if d.status == "pending"]

    @staticmethod
    def list_all() -> List[DraftEmail]:
        return list(_drafts.values())

    @staticmethod
    async def approve(draft_id: str, reviewer: str) -> Optional[DraftEmail]:
        draft = _drafts.get(draft_id)
        if draft is None:
            return None
        if draft.status != "pending":
            return draft

        draft.status = "approved"
        draft.reviewed_by = reviewer
        draft.reviewed_at = datetime.utcnow()

        await AuditLog.append("draft_approved", {
            "draft_id": draft_id,
            "reviewer": reviewer,
            "candidate_id": draft.candidate_id,
        })
        return draft

    @staticmethod
    async def reject(draft_id: str, reviewer: str) -> Optional[DraftEmail]:
        draft = _drafts.get(draft_id)
        if draft is None:
            return None
        if draft.status != "pending":
            return draft

        draft.status = "rejected"
        draft.reviewed_by = reviewer
        draft.reviewed_at = datetime.utcnow()

        await AuditLog.append("draft_rejected", {
            "draft_id": draft_id,
            "reviewer": reviewer,
            "candidate_id": draft.candidate_id,
        })
        return draft

    @staticmethod
    async def mark_sent(draft_id: str) -> Optional[DraftEmail]:
        draft = _drafts.get(draft_id)
        if draft and draft.status == "approved":
            draft.status = "sent"
            await AuditLog.append("draft_sent", {"draft_id": draft_id})
        return draft
