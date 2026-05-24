from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, validator

class ReplyClassifierOutput(BaseModel):
    """Schema for Reply Classifier agent output."""
    intent: Literal["INTERESTED", "QUESTION", "SCHEDULING", "TASK_SUBMISSION", "DECLINE", "OTHER"]
    confidence: float
    extracted: dict
    summary: str
    
    @validator("confidence")
    def confidence_valid(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be 0.0–1.0")
        return v
    
    def is_high_confidence(self) -> bool:
        """Check if confidence is sufficient to auto-process."""
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

class EvaluationAgentOutput(BaseModel):
    """Schema for Evaluation Agent output."""
    dimension_scores: Dict[str, float]
    composite: float
    evidence_summary: str
    red_flags: List[str]
    candidate_feedback_draft: str
    
    @validator("composite")
    def composite_valid(cls, v):
        if not 0.0 <= v <= 10.0:
            raise ValueError("composite must be 0–10")
        return v
