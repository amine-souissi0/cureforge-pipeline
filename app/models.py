import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator
from app.fsm import CandidateState


class CandidateModel(BaseModel):
    """Pydantic model for candidate records."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: str
    github_handle: Optional[str] = None
    role: str = "Software Engineer"
    level: str = "senior"
    background_notes: Optional[str] = None
    candidate_profile: Optional[Dict[str, Any]] = None
    confirmed_jd_id: Optional[str] = None
    location: Optional[str] = None
    notice_period: Optional[str] = None
    preferred_roles: Optional[List[str]] = None
    source: Literal["founder_added", "email_forwarded"] = "founder_added"
    state: CandidateState = CandidateState.NEW
    round: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("Invalid email")
        return v.lower()


class MessageModel(BaseModel):
    """Pydantic model for email messages."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_id: str
    direction: Literal["INBOUND", "OUTBOUND"]
    template_id: Optional[str] = None
    body: str
    sent_by_agent: bool = False
    approved_by: Optional[str] = None
    gmail_id: Optional[str] = None
    ts: datetime = Field(default_factory=datetime.utcnow)


class TaskModel(BaseModel):
    """Pydantic model for generated tasks."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_id: str
    candidate_brief: str
    internal_spec: Dict[str, Any]
    repo_url: Optional[str] = None
    corpus_ref: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvaluationModel(BaseModel):
    """Pydantic model for evaluation records."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_id: str
    round: int
    submission_sha: str
    dimension_scores: Dict[str, float]
    composite: float
    evidence: Dict[str, Any]
    red_flags: Optional[List[str]] = None
    feedback_draft: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("composite")
    @classmethod
    def composite_valid(cls, v: float) -> float:
        if not 0.0 <= v <= 10.0:
            raise ValueError("composite must be between 0 and 10")
        return v


class TransitionModel(BaseModel):
    """Pydantic model for FSM transitions."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_id: str
    from_state: CandidateState
    to_state: CandidateState
    predicate: str
    actor: str
    ts: datetime = Field(default_factory=datetime.utcnow)


class AuditLogModel(BaseModel):
    """Pydantic model for immutable audit log."""
    id: int
    candidate_id: Optional[str] = None
    event_type: str
    actor: str
    inputs: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None
    ts: datetime = Field(default_factory=datetime.utcnow)
