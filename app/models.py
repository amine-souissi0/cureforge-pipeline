import uuid
from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, validator
from app.fsm import CandidateState

class CandidateModel(BaseModel):
    """Pydantic model for candidate records."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: str
    github_handle: Optional[str] = None
    source: Literal["founder_added", "email_forwarded"] = "founder_added"
    state: CandidateState = CandidateState.NEW
    round: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    @validator("email")
    def email_valid(cls, v):
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
    approved_by: Optional[str] = None  # Founder identifier
    gmail_id: Optional[str] = None
    ts: datetime = Field(default_factory=datetime.utcnow)

class TaskModel(BaseModel):
    """Pydantic model for generated tasks."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_id: str
    candidate_brief: str
    internal_spec: dict  # Holds expected_behavior, held_out_tests, failure_modes
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
    evidence: dict
    red_flags: Optional[List[str]] = None
    feedback_draft: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    @validator("composite")
    def composite_valid(cls, v):
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
    id: int  # Auto-increment, never mutated
    candidate_id: Optional[str] = None
    event_type: str
    actor: str
    inputs: Optional[dict] = None
    outputs: Optional[dict] = None
    ts: datetime = Field(default_factory=datetime.utcnow)
