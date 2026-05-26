from typing import List, Optional

from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models import TaskModel
from app.orm_models import TaskRow
from app.schemas import AuditLog


def _row_to_model(row: TaskRow) -> TaskModel:
    return TaskModel(
        id=row.id,
        candidate_id=row.candidate_id,
        candidate_brief=row.candidate_brief,
        internal_spec=row.internal_spec or {},
        repo_url=row.repo_url,
        corpus_ref=row.corpus_ref,
        created_at=row.created_at,
    )


class TaskStore:
    @staticmethod
    async def add(task: TaskModel) -> str:
        async with AsyncSessionLocal() as session:
            row = TaskRow(
                id=task.id,
                candidate_id=task.candidate_id,
                candidate_brief=task.candidate_brief,
                internal_spec=task.internal_spec,
                repo_url=task.repo_url,
                corpus_ref=task.corpus_ref,
                created_at=task.created_at,
            )
            session.add(row)
            await session.commit()
        await AuditLog.append("task_stored", {
            "task_id": task.id,
            "candidate_id": task.candidate_id,
            "corpus_ref": task.corpus_ref,
        })
        return task.id

    @staticmethod
    async def get_by_id(task_id: str) -> Optional[TaskModel]:
        async with AsyncSessionLocal() as session:
            row = await session.get(TaskRow, task_id)
            return _row_to_model(row) if row else None

    @staticmethod
    async def get_by_candidate(candidate_id: str) -> Optional[TaskModel]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TaskRow)
                .where(TaskRow.candidate_id == candidate_id)
                .order_by(TaskRow.created_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return _row_to_model(row) if row else None

    @staticmethod
    async def update_repo_url(task_id: str, repo_url: str) -> Optional[TaskModel]:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(TaskRow)
                .where(TaskRow.id == task_id)
                .values(repo_url=repo_url)
            )
            await session.commit()
            row = await session.get(TaskRow, task_id)
        if row:
            await AuditLog.append("task_repo_provisioned", {
                "task_id": task_id,
                "repo_url": repo_url,
            })
        return _row_to_model(row) if row else None

    @staticmethod
    async def list_all() -> List[TaskModel]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(TaskRow))
            return [_row_to_model(r) for r in result.scalars().all()]
