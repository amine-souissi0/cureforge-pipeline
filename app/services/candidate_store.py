from typing import Dict, List, Optional

from app.fsm import CandidateState
from app.models import CandidateModel
from app.schemas import AuditLog

_candidates: Dict[str, CandidateModel] = {}


class CandidateStore:
    @staticmethod
    async def add(candidate: CandidateModel) -> str:
        _candidates[candidate.id] = candidate
        await AuditLog.append("candidate_stored", {
            "candidate_id": candidate.id,
            "email": candidate.email,
        })
        return candidate.id

    @staticmethod
    def get_by_id(candidate_id: str) -> Optional[CandidateModel]:
        return _candidates.get(candidate_id)

    @staticmethod
    def get_by_email(email: str) -> Optional[CandidateModel]:
        email = email.lower()
        return next((c for c in _candidates.values() if c.email == email), None)

    @staticmethod
    def list_all() -> List[CandidateModel]:
        return list(_candidates.values())

    @staticmethod
    async def update_state(candidate_id: str, state: CandidateState) -> Optional[CandidateModel]:
        candidate = _candidates.get(candidate_id)
        if candidate is None:
            return None
        updated = candidate.model_copy(update={"state": state})
        _candidates[candidate_id] = updated
        return updated

    @staticmethod
    def count_by_state() -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for c in _candidates.values():
            key = c.state.value
            counts[key] = counts.get(key, 0) + 1
        return counts
