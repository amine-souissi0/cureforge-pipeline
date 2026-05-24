from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, field_validator


class AuditLog:
    """
    Audit log — writes to DB for persistence and keeps an in-memory list
    for the current session (used by /health/costs and /health/checklist).
    """
    _log: List[Dict[str, Any]] = []

    @staticmethod
    async def append(event_type: str, data: Dict[str, Any]) -> None:
        AuditLog._log.append({"event_type": event_type, "data": data})
        try:
            from app.database import AsyncSessionLocal
            from app.orm_models import AuditLogRow
            async with AsyncSessionLocal() as session:
                row = AuditLogRow(event_type=event_type, data=data)
                session.add(row)
                await session.commit()
        except Exception:
            pass  # DB unavailable during early startup — in-memory log still works


class Message(BaseModel):
    """Inbound email message DTO from Gmail."""
    id: str
    candidate_id: str
    subject: str
    body: str
    message_id: str


class ReplyClassifierOutput(BaseModel):
    """Schema for Reply Classifier agent output."""
    intent: Literal["INTERESTED", "QUESTION", "SCHEDULING", "TASK_SUBMISSION", "DECLINE", "OTHER"]
    confidence: float
    extracted: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    reasoning: Optional[str] = None

    @field_validator("confidence")
    @classmethod
    def confidence_valid(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be 0.0–1.0")
        return v

    def is_high_confidence(self) -> bool:
        return self.confidence >= 0.75 and self.intent != "OTHER"


class HeldOutTest(BaseModel):
    """Represents a held-out test case."""
    test_id: str
    input: str
    expected_output: str


class InternalTaskSpec(BaseModel):
    """Internal task specification (never candidate-facing)."""
    expected_behavior: str
    held_out_tests: List[HeldOutTest]
    failure_modes: List[str]


class TaskDecomposerOutput(BaseModel):
    """Schema for Task Decomposer agent output."""
    success: bool
    corpus_pattern_selected: str
    abstraction_verified: bool
    blocklist_check: Literal["PASS", "FAIL", "AMBIGUOUS"]
    candidate_brief: str
    internal_spec: Optional[InternalTaskSpec] = None


class TemplateResponderOutput(BaseModel):
    """Schema for Template Responder agent output."""
    template_id: str
    subject: str
    body: str
    fields_used: List[str]
    constraint_check: Literal["PASS", "FAIL"]


class EvaluationAgentOutput(BaseModel):
    """Schema for Evaluation Agent output."""
    dimension_scores: Dict[str, float]
    composite: float
    evidence_summary: str
    red_flags: List[str]
    candidate_feedback_draft: str

    @field_validator("composite")
    @classmethod
    def composite_valid(cls, v: float) -> float:
        if not 0.0 <= v <= 10.0:
            raise ValueError("composite must be 0–10")
        return v


class OfferDrafterOutput(BaseModel):
    """Schema for Offer Drafter agent output."""
    role: str
    offer_details: str       # Rendered body for the offer-cover template
    compensation_summary: str  # Internal summary — never sent to candidate
    constraint_check: Literal["PASS", "FAIL"]
