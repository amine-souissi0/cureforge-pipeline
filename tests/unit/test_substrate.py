import pytest
import asyncio
from app.fsm import FSMEngine, CandidateState
from app.schemas import ReplyClassifierOutput, EvaluationAgentOutput
from app.models import CandidateModel

@pytest.mark.asyncio
async def test_fsm_transitions():
    """Test FSM transition table and predicates."""
    fsm = FSMEngine()
    
    # Test 1: NEW → ENGAGED (intake_complete predicate)
    result = await fsm.transition(
        candidate_id="test_candidate_1",
        target_state=CandidateState.ENGAGED,
        context={"intake_complete": True},
        actor="intake_agent"
    )
    assert result, "Should allow NEW → ENGAGED with intake_complete=True"
    
    # Test 2: NEW → ENGAGED without predicate (should fail)
    result = await fsm.transition(
        candidate_id="test_candidate_2",
        target_state=CandidateState.ENGAGED,
        context={"intake_complete": False},
        actor="intake_agent"
    )
    assert not result, "Should reject NEW → ENGAGED with intake_complete=False"
    
    # Test 3: Invalid transition (should fail)
    result = await fsm.transition(
        candidate_id="test_candidate_3",
        target_state=CandidateState.HIRED,  # Can't jump directly to HIRED from NEW
        context={},
        actor="founder"
    )
    assert not result, "Should reject invalid NEW → HIRED"

def test_schema_validation():
    """Test schema validators for agent outputs."""
    # Test 1: Valid classifier output
    valid_classifier = {
        "intent": "INTERESTED",
        "confidence": 0.95,
        "extracted": {"questions": []},
        "summary": "Candidate interested"
    }
    output = ReplyClassifierOutput(**valid_classifier)
    assert output.is_high_confidence(), "Should detect high confidence"
    
    # Test 2: Invalid classifier (confidence out of range)
    invalid_classifier = {
        "intent": "INTERESTED",
        "confidence": 1.5,  # Out of range
        "extracted": {},
        "summary": "Bad"
    }
    with pytest.raises(ValueError):
        ReplyClassifierOutput(**invalid_classifier)
    
    # Test 3: Valid evaluation output
    valid_eval = {
        "dimension_scores": {
            "correctness_verification": 8.5,
            "invariant_failclosed_discipline": 8.0,
            "structure_determinism": 7.5,
            "testing_instrumentation": 8.0,
            "communication_iteration": 7.0,
        },
        "composite": 8.1,
        "evidence_summary": "Strong submission",
        "red_flags": [],
        "candidate_feedback_draft": "Your solution was mostly correct..."
    }
    output = EvaluationAgentOutput(**valid_eval)
    assert output.composite == 8.1, "Should parse composite score"

def test_candidate_model():
    """Test Pydantic candidate model."""
    # Test 1: Valid candidate
    candidate = CandidateModel(name="John Doe", email="john@example.com")
    assert candidate.state == CandidateState.NEW, "Default state should be NEW"
    assert candidate.email == "john@example.com", "Email should be lowercase"
    
    # Test 2: Invalid email
    with pytest.raises(ValueError):
        CandidateModel(name="Jane", email="invalid_email")
