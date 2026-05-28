from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

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
        role=row.role if row.role else "Software Engineer",
        level=row.level if row.level else "senior",
        background_notes=row.background_notes,
        candidate_profile=row.candidate_profile,
        confirmed_jd_id=row.confirmed_jd_id,
        location=row.location,
        notice_period=row.notice_period,
        preferred_roles=row.preferred_roles,
        source=row.source,  # type: ignore[arg-type]
        state=CandidateState(row.state),
        round=row.round,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class CandidateStore:
    @staticmethod
    async def add(candidate: CandidateModel) -> str:
        from fastapi import HTTPException
        async with AsyncSessionLocal() as session:
            row = CandidateRow(
                id=candidate.id,
                name=candidate.name,
                email=candidate.email,
                github_handle=candidate.github_handle,
                role=candidate.role,
                level=candidate.level,
                background_notes=candidate.background_notes,
                candidate_profile=candidate.candidate_profile,
                confirmed_jd_id=candidate.confirmed_jd_id,
                location=candidate.location,
                notice_period=candidate.notice_period,
                preferred_roles=candidate.preferred_roles,
                source=candidate.source,
                state=candidate.state.value,
                round=candidate.round,
                created_at=candidate.created_at,
                updated_at=candidate.updated_at,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise HTTPException(status_code=409, detail=f"Candidate with email {candidate.email!r} already exists.")
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
    async def update_background(candidate_id: str, background_notes: str, level: str) -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(CandidateRow)
                .where(CandidateRow.id == candidate_id)
                .values(background_notes=background_notes, level=level, updated_at=datetime.utcnow())
            )
            await session.commit()

    @staticmethod
    async def update_profile(
        candidate_id: str,
        candidate_profile: dict,
        background_notes: str,
        level: str,
        location: Optional[str] = None,
        notice_period: Optional[str] = None,
        preferred_roles: Optional[List] = None,
    ) -> None:
        async with AsyncSessionLocal() as session:
            values: dict = dict(
                candidate_profile=candidate_profile,
                background_notes=background_notes,
                level=level,
                updated_at=datetime.utcnow(),
            )
            if location is not None:
                values["location"] = location
            if notice_period is not None:
                values["notice_period"] = notice_period
            if preferred_roles is not None:
                values["preferred_roles"] = preferred_roles
            await session.execute(
                update(CandidateRow)
                .where(CandidateRow.id == candidate_id)
                .values(**values)
            )
            await session.commit()

    @staticmethod
    async def update_confirmed_jd(candidate_id: str, jd_id: str) -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(CandidateRow)
                .where(CandidateRow.id == candidate_id)
                .values(confirmed_jd_id=jd_id, updated_at=datetime.utcnow())
            )
            await session.commit()

    @staticmethod
    async def count_by_state() -> Dict[str, int]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CandidateRow.state, func.count()).group_by(CandidateRow.state)
            )
            return {state: count for state, count in result.all()}
