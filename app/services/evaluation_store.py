from typing import List, Optional

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models import EvaluationModel
from app.orm_models import EvaluationRow
from app.schemas import AuditLog


def _row_to_model(row: EvaluationRow) -> EvaluationModel:
    return EvaluationModel(
        id=row.id,
        candidate_id=row.candidate_id,
        round=row.round,
        submission_sha=row.submission_sha,
        dimension_scores=row.dimension_scores or {},
        composite=row.composite,
        evidence=row.evidence or {},
        red_flags=row.red_flags,
        feedback_draft=row.feedback_draft,
        created_at=row.created_at,
    )


class EvaluationStore:
    @staticmethod
    async def add(evaluation: EvaluationModel) -> str:
        async with AsyncSessionLocal() as session:
            row = EvaluationRow(
                id=evaluation.id,
                candidate_id=evaluation.candidate_id,
                round=evaluation.round,
                submission_sha=evaluation.submission_sha,
                dimension_scores=evaluation.dimension_scores,
                composite=evaluation.composite,
                evidence=evaluation.evidence,
                red_flags=evaluation.red_flags,
                feedback_draft=evaluation.feedback_draft,
                created_at=evaluation.created_at,
            )
            session.add(row)
            await session.commit()
        await AuditLog.append("evaluation_stored", {
            "evaluation_id": evaluation.id,
            "candidate_id": evaluation.candidate_id,
            "round": evaluation.round,
            "composite": evaluation.composite,
        })
        return evaluation.id

    @staticmethod
    async def get_by_id(evaluation_id: str) -> Optional[EvaluationModel]:
        async with AsyncSessionLocal() as session:
            row = await session.get(EvaluationRow, evaluation_id)
            return _row_to_model(row) if row else None

    @staticmethod
    async def get_latest_by_candidate(candidate_id: str) -> Optional[EvaluationModel]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(EvaluationRow)
                .where(EvaluationRow.candidate_id == candidate_id)
                .order_by(EvaluationRow.round.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return _row_to_model(row) if row else None

    @staticmethod
    async def list_by_candidate(candidate_id: str) -> List[EvaluationModel]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(EvaluationRow)
                .where(EvaluationRow.candidate_id == candidate_id)
                .order_by(EvaluationRow.round.asc())
            )
            return [_row_to_model(r) for r in result.scalars().all()]

    @staticmethod
    async def get_round_count(candidate_id: str) -> int:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(func.count()).where(EvaluationRow.candidate_id == candidate_id)
            )
            return result.scalar_one() or 0
