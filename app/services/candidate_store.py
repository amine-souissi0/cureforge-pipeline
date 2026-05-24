from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func, select, update

from app.database import AsyncSessionLocal
from app.fsm import CandidateState
from app.models import CandidateModel
from app.orm_models import CandidateRow


def _row_to_model(row: CandidateRow) -> CandidateModel:
    return CandidateModel(
        id=row.id,
        name=row.name,
        email=row.email,
        github_handle=row.github_handle,
        source=row.source,  # type: ignore[arg-type]
        state=CandidateState(row.state),
        round=row.round,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class CandidateStore:
    @staticmethod
    async def add(candidate: CandidateModel) -> str:
        async with AsyncSessionLocal() as session:
            row = CandidateRow(
                id=candidate.id,
                name=candidate.name,
                email=candidate.email,
                github_handle=candidate.github_handle,
                source=candidate.source,
                state=candidate.state.value,
                round=candidate.round,
                created_at=candidate.created_at,
                updated_at=candidate.updated_at,
            )
            session.add(row)
            await session.commit()
        return candidate.id

    @staticmethod
    async def get_by_id(candidate_id: str) -> Optional[CandidateModel]:
        async with AsyncSessionLocal() as session:
            row = await session.get(CandidateRow, candidate_id)
            return _row_to_model(row) if row else None

    @staticmethod
    async def get_by_email(email: str) -> Optional[CandidateModel]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CandidateRow).where(CandidateRow.email == email.lower())
            )
            row = result.scalar_one_or_none()
            return _row_to_model(row) if row else None

    @staticmethod
    async def list_all() -> List[CandidateModel]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(CandidateRow))
            return [_row_to_model(r) for r in result.scalars().all()]

    @staticmethod
    async def update_state(candidate_id: str, state: CandidateState) -> Optional[CandidateModel]:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(CandidateRow)
                .where(CandidateRow.id == candidate_id)
                .values(state=state.value, updated_at=datetime.utcnow())
            )
            await session.commit()
            row = await session.get(CandidateRow, candidate_id)
            return _row_to_model(row) if row else None

    @staticmethod
    async def count_by_state() -> Dict[str, int]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CandidateRow.state, func.count()).group_by(CandidateRow.state)
            )
            return {state: count for state, count in result.all()}
