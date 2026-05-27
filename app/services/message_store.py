"""§11 messages table — log every inbound and outbound email."""
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.orm_models import MessageRow


class MessageStore:
    @staticmethod
    async def log_inbound(
        candidate_id: str,
        body: str,
        subject: Optional[str] = None,
        gmail_id: Optional[str] = None,
    ) -> str:
        msg_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as session:
            row = MessageRow(
                id=msg_id,
                candidate_id=candidate_id,
                direction="inbound",
                subject=subject,
                body=body,
                sent_by_agent=False,
                gmail_id=gmail_id,
                created_at=datetime.utcnow(),
            )
            session.add(row)
            await session.commit()
        return msg_id

    @staticmethod
    async def log_outbound(
        candidate_id: str,
        body: str,
        subject: Optional[str] = None,
        template_id: Optional[str] = None,
        approved_by: Optional[str] = None,
        gmail_id: Optional[str] = None,
    ) -> str:
        msg_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as session:
            row = MessageRow(
                id=msg_id,
                candidate_id=candidate_id,
                direction="outbound",
                template_id=template_id,
                subject=subject,
                body=body,
                sent_by_agent=True,
                approved_by=approved_by,
                gmail_id=gmail_id,
                created_at=datetime.utcnow(),
            )
            session.add(row)
            await session.commit()
        return msg_id

    @staticmethod
    async def list_by_candidate(candidate_id: str) -> List[MessageRow]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(MessageRow)
                .where(MessageRow.candidate_id == candidate_id)
                .order_by(MessageRow.created_at)
            )
            return list(result.scalars().all())
