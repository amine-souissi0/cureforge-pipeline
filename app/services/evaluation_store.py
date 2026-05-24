from typing import Dict, List, Optional

from app.models import EvaluationModel
from app.schemas import AuditLog

_evaluations: Dict[str, EvaluationModel] = {}
_candidate_index: Dict[str, List[str]] = {}  # candidate_id → [eval_id, ...]


class EvaluationStore:
    @staticmethod
    async def add(evaluation: EvaluationModel) -> str:
        _evaluations[evaluation.id] = evaluation
        _candidate_index.setdefault(evaluation.candidate_id, []).append(evaluation.id)
        await AuditLog.append("evaluation_stored", {
            "evaluation_id": evaluation.id,
            "candidate_id": evaluation.candidate_id,
            "round": evaluation.round,
            "composite": evaluation.composite,
        })
        return evaluation.id

    @staticmethod
    def get_by_id(evaluation_id: str) -> Optional[EvaluationModel]:
        return _evaluations.get(evaluation_id)

    @staticmethod
    def get_latest_by_candidate(candidate_id: str) -> Optional[EvaluationModel]:
        ids = _candidate_index.get(candidate_id, [])
        if not ids:
            return None
        return _evaluations.get(ids[-1])

    @staticmethod
    def list_by_candidate(candidate_id: str) -> List[EvaluationModel]:
        ids = _candidate_index.get(candidate_id, [])
        return [_evaluations[eid] for eid in ids if eid in _evaluations]

    @staticmethod
    def get_round_count(candidate_id: str) -> int:
        return len(_candidate_index.get(candidate_id, []))
