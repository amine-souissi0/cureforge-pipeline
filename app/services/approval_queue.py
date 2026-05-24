from datetime import datetime
from typing import List, Literal, Optional
import uuid

from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.orm_models import DraftEmailRow
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


def _row_to_draft(row: DraftEmailRow) -> DraftEmail:
    return DraftEmail(
        draft_id=row.draft_id,
        candidate_id=row.candidate_id,
        template_id=row.template_id,
        subject=row.subject,
        body=row.body,
        to_email=row.to_email,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
    )


class ApprovalQueue:
    @staticmethod
    async def add(draft: DraftEmail) -> str:
        async with AsyncSessionLocal() as session:
            row = DraftEmailRow(
                draft_id=draft.draft_id,
                candidate_id=draft.candidate_id,
                template_id=draft.template_id,
                subject=draft.subject,
                body=draft.body,
                to_email=draft.to_email,
                status=draft.status,
                created_at=draft.created_at,
                reviewed_by=draft.reviewed_by,
                reviewed_at=draft.reviewed_at,
            )
            session.add(row)
            await session.commit()
        await AuditLog.append("draft_created", {
            "draft_id": draft.draft_id,
            "candidate_id": draft.candidate_id,
            "template_id": draft.template_id,
        })
        return draft.draft_id

    @staticmethod
    async def get(draft_id: str) -> Optional[DraftEmail]:
        async with AsyncSessionLocal() as session:
            row = await session.get(DraftEmailRow, draft_id)
            return _row_to_draft(row) if row else None

    @staticmethod
    async def list_pending() -> List[DraftEmail]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(DraftEmailRow).where(DraftEmailRow.status == "pending")
            )
            return [_row_to_draft(r) for r in result.scalars().all()]

    @staticmethod
    async def list_all() -> List[DraftEmail]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(DraftEmailRow))
            return [_row_to_draft(r) for r in result.scalars().all()]

    @staticmethod
    async def approve(draft_id: str, reviewer: str) -> Optional[DraftEmail]:
        async with AsyncSessionLocal() as session:
            row = await session.get(DraftEmailRow, draft_id)
            if row is None or row.status != "pending":
                return _row_to_draft(row) if row else None
            await session.execute(
                update(DraftEmailRow)
                .where(DraftEmailRow.draft_id == draft_id)
                .values(status="approved", reviewed_by=reviewer, reviewed_at=datetime.utcnow())
            )
            await session.commit()
            row = await session.get(DraftEmailRow, draft_id)
        await AuditLog.append("draft_approved", {
            "draft_id": draft_id,
            "reviewer": reviewer,
        })
        return _row_to_draft(row) if row else None

    @staticmethod
    async def reject(draft_id: str, reviewer: str) -> Optional[DraftEmail]:
        async with AsyncSessionLocal() as session:
            row = await session.get(DraftEmailRow, draft_id)
            if row is None or row.status != "pending":
                return _row_to_draft(row) if row else None
            await session.execute(
                update(DraftEmailRow)
                .where(DraftEmailRow.draft_id == draft_id)
                .values(status="rejected", reviewed_by=reviewer, reviewed_at=datetime.utcnow())
            )
            await session.commit()
            row = await session.get(DraftEmailRow, draft_id)
        await AuditLog.append("draft_rejected", {
            "draft_id": draft_id,
            "reviewer": reviewer,
        })
        return _row_to_draft(row) if row else None

    @staticmethod
    async def mark_sent(draft_id: str) -> Optional[DraftEmail]:
        async with AsyncSessionLocal() as session:
            row = await session.get(DraftEmailRow, draft_id)
            if row and row.status == "approved":
                await session.execute(
                    update(DraftEmailRow)
                    .where(DraftEmailRow.draft_id == draft_id)
                    .values(status="sent")
                )
                await session.commit()
                row = await session.get(DraftEmailRow, draft_id)
            await AuditLog.append("draft_sent", {"draft_id": draft_id})
        return _row_to_draft(row) if row else None
