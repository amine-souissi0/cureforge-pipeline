from typing import Dict, List, Optional

from app.models import TaskModel
from app.schemas import AuditLog

# In-memory store. Swap for Redis or DB-backed store in production.
_tasks: Dict[str, TaskModel] = {}
_candidate_index: Dict[str, str] = {}  # candidate_id → task_id


class TaskStore:
    @staticmethod
    async def add(task: TaskModel) -> str:
        _tasks[task.id] = task
        _candidate_index[task.candidate_id] = task.id
        await AuditLog.append("task_stored", {
            "task_id": task.id,
            "candidate_id": task.candidate_id,
            "corpus_ref": task.corpus_ref,
        })
        return task.id

    @staticmethod
    def get_by_id(task_id: str) -> Optional[TaskModel]:
        return _tasks.get(task_id)

    @staticmethod
    def get_by_candidate(candidate_id: str) -> Optional[TaskModel]:
        task_id = _candidate_index.get(candidate_id)
        if task_id is None:
            return None
        return _tasks.get(task_id)

    @staticmethod
    async def update_repo_url(task_id: str, repo_url: str) -> Optional[TaskModel]:
        task = _tasks.get(task_id)
        if task is None:
            return None
        updated = task.model_copy(update={"repo_url": repo_url})
        _tasks[task_id] = updated
        await AuditLog.append("task_repo_provisioned", {
            "task_id": task_id,
            "repo_url": repo_url,
        })
        return updated

    @staticmethod
    def list_all() -> List[TaskModel]:
        return list(_tasks.values())
