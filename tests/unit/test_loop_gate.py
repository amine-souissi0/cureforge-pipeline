import json
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.fsm import CandidateState
from app.models import EvaluationModel, TaskModel
from app.services.decision_engine import decide, Decision, MAX_RESUBMISSION_ROUNDS
from app.services.evaluation_store import EvaluationStore
from app.services.task_store import TaskStore
from config.rubric import HIRE_THRESHOLD, RESUBMIT_THRESHOLD

from tests.conftest import TEST_AUTH
client = TestClient(app, headers=TEST_AUTH)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _store_evaluation(candidate_id: str, composite: float, round_num: int = 1) -> str:
    ev = EvaluationModel(
        candidate_id=candidate_id,
        round=round_num,
        submission_sha=f"sha-{round_num}",
        dimension_scores={"correctness_verification": composite},
        composite=composite,
        evidence={},
        feedback_draft=(
            f"Your submission passed key tests. "
            f"Upgrade ask: add error handling for edge cases."
        ),
    )
    return await EvaluationStore.add(ev)


async def _store_task(candidate_id: str) -> TaskModel:
    task = TaskModel(
        candidate_id=candidate_id,
        candidate_brief="Build a rate limiter.",
        internal_spec={
            "expected_behavior": "correct",
            "held_out_tests": [
                {"test_id": "t1", "input": "1 + 1", "expected_output": "2"},
            ],
            "failure_modes": [],
        },
        corpus_ref="rate_limiter",
    )
    await TaskStore.add(task)
    return task


def _valid_eval_payload(composite: float = 8.0) -> str:
    return json.dumps({
        "dimension_scores": {d: composite for d in [
            "correctness_verification", "invariant_failclosed_discipline",
            "structure_determinism", "testing_instrumentation", "communication_iteration",
        ]},
        "composite": composite,
        "evidence_summary": "Good submission.",
        "red_flags": [],
        "candidate_feedback_draft": (
            "Your solution passed 3 of 4 tests. "
            "Upgrade ask: add thread-safety verification."
        ),
    })


def _mock_opus(payload: str) -> MagicMock:
    block = MagicMock()
    block.text = payload
    resp = MagicMock()
    resp.content = [block]
    resp.usage.input_tokens = 400
    resp.usage.output_tokens = 500
    inst = MagicMock()
    inst.messages.create = AsyncMock(return_value=resp)
    return inst


def _mock_haiku(payload: str) -> MagicMock:
    block = MagicMock()
    block.text = payload
    resp = MagicMock()
    resp.content = [block]
    resp.usage.input_tokens = 80
    resp.usage.output_tokens = 150
    inst = MagicMock()
    inst.messages.create = AsyncMock(return_value=resp)
    return inst


# ---------------------------------------------------------------------------
# Decision Engine — all branches
# ---------------------------------------------------------------------------

def test_decide_hire_recommend():
    d = decide(composite=8.5, rounds_completed=1, mode="recommend")
    assert d.next_state == CandidateState.HIRE_RECOMMENDED
    assert d.requires_founder_approval is True


def test_decide_hire_autonomous():
    d = decide(composite=9.0, rounds_completed=1, mode="autonomous")
    assert d.next_state == CandidateState.HIRED
    assert d.requires_founder_approval is False


def test_decide_resubmit_mid_range():
    d = decide(composite=7.5, rounds_completed=1)
    assert d.next_state == CandidateState.AWAITING_RESUBMISSION
    assert d.requires_founder_approval is False


def test_decide_resubmit_exactly_at_threshold():
    d = decide(composite=RESUBMIT_THRESHOLD, rounds_completed=1)
    assert d.next_state == CandidateState.AWAITING_RESUBMISSION


def test_decide_warm_hold_low_composite_max_rounds():
    d = decide(composite=5.0, rounds_completed=MAX_RESUBMISSION_ROUNDS)
    assert d.next_state == CandidateState.WARM_HOLD
    assert d.requires_founder_approval is False


def test_decide_resubmit_low_composite_first_round():
    d = decide(composite=5.0, rounds_completed=1)
    assert d.next_state == CandidateState.AWAITING_RESUBMISSION


def test_decide_exactly_at_hire_threshold():
    d = decide(composite=HIRE_THRESHOLD, rounds_completed=1)
    assert d.next_state == CandidateState.HIRE_RECOMMENDED


def test_decide_reasoning_is_informative():
    d = decide(composite=8.7, rounds_completed=1)
    assert "8.7" in d.reasoning or "8.70" in d.reasoning


def test_decide_fsm_context_has_composite():
    d = decide(composite=7.2, rounds_completed=1)
    assert "composite" in d.fsm_context


# ---------------------------------------------------------------------------
# Feedback Controller — mocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feedback_controller_resubmit_path():
    candidate_id = "cand-fc-resubmit"
    ev_id = await _store_evaluation(candidate_id, composite=7.5, round_num=1)

    template_payload = json.dumps({
        "template_id": "feedback-delivery",
        "subject": "Feedback on Your Submission",
        "body": "Hi cand-fc-resubmit,\n\nGood work. Upgrade ask: add error handling.",
        "fields_used": ["candidate_name", "feedback", "upgrade_ask", "sender_name"],
        "constraint_check": "PASS",
    })

    with patch("anthropic.AsyncAnthropic", return_value=_mock_haiku(template_payload)):
        with patch("app.agents.template_responder.get_anthropic_api_key", return_value="test-key"):
            from app.services.feedback_controller import run_feedback_loop
            result = await run_feedback_loop(
                candidate_id=candidate_id,
                evaluation_id=ev_id,
                to_email="cand@example.com",
            )

    assert result.decision.next_state == CandidateState.AWAITING_RESUBMISSION
    assert result.composite == 7.5
    assert result.feedback_draft_id is not None  # draft mode by default


@pytest.mark.asyncio
async def test_feedback_controller_warm_hold_path():
    candidate_id = "cand-fc-warmhold"
    # Store 2 evaluations so rounds_completed = 2
    await _store_evaluation(candidate_id, composite=5.0, round_num=1)
    ev_id = await _store_evaluation(candidate_id, composite=4.5, round_num=2)

    template_payload_feedback = json.dumps({
        "template_id": "feedback-delivery",
        "subject": "Feedback",
        "body": "Hi cand-fc-warmhold,\n\nHere is feedback. Upgrade ask: be more thorough.",
        "fields_used": ["candidate_name", "feedback", "upgrade_ask", "sender_name"],
        "constraint_check": "PASS",
    })
    template_payload_warmhold = json.dumps({
        "template_id": "warm-hold",
        "subject": "Staying in Touch",
        "body": "Hi cand-fc-warmhold,\n\nThank you for your time.",
        "fields_used": ["candidate_name", "sender_name"],
        "constraint_check": "PASS",
    })

    call_count = 0

    async def _mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        payload = template_payload_feedback if call_count == 1 else template_payload_warmhold
        block = MagicMock()
        block.text = payload
        resp = MagicMock()
        resp.content = [block]
        resp.usage.input_tokens = 80
        resp.usage.output_tokens = 100
        return resp

    mock_instance = MagicMock()
    mock_instance.messages.create = _mock_create

    with patch("anthropic.AsyncAnthropic", return_value=mock_instance):
        with patch("app.agents.template_responder.get_anthropic_api_key", return_value="test-key"):
            from app.services.feedback_controller import run_feedback_loop
            result = await run_feedback_loop(
                candidate_id=candidate_id,
                evaluation_id=ev_id,
                to_email="cand@example.com",
            )

    assert result.decision.next_state == CandidateState.WARM_HOLD


# ---------------------------------------------------------------------------
# Gate API endpoints
# ---------------------------------------------------------------------------

def test_gate_status_no_evaluations():
    response = client.get("/gate/nobody/status")
    assert response.status_code == 200
    data = response.json()
    assert data["rounds_completed"] == 0
    assert data["latest_composite"] is None


def test_gate_status_with_evaluations():
    candidate_id = "cand-gate-status"
    asyncio.get_event_loop().run_until_complete(
        _store_evaluation(candidate_id, composite=8.0, round_num=1)
    )
    response = client.get(f"/gate/{candidate_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["rounds_completed"] == 1
    assert data["latest_composite"] == 8.0
    assert "projected_next_state" in data


def test_gate_decide_evaluation_not_found():
    response = client.post("/gate/cand-x/decide", json={
        "evaluation_id": "nonexistent-eval",
        "to_email": "x@example.com",
    })
    assert response.status_code == 404


def test_gate_decide_wrong_candidate():
    candidate_id = "cand-gate-wrong"
    ev_id = asyncio.get_event_loop().run_until_complete(
        _store_evaluation(candidate_id, composite=7.5)
    )
    response = client.post("/gate/different-candidate/decide", json={
        "evaluation_id": ev_id,
        "to_email": "x@example.com",
    })
    assert response.status_code == 400


def test_gate_decide_success():
    candidate_id = "cand-gate-decide"
    ev_id = asyncio.get_event_loop().run_until_complete(
        _store_evaluation(candidate_id, composite=7.5)
    )

    template_payload = json.dumps({
        "template_id": "feedback-delivery",
        "subject": "Feedback",
        "body": "Hi cand-gate-decide,\n\nGood work. Upgrade ask: add tests.",
        "fields_used": ["candidate_name", "feedback", "upgrade_ask", "sender_name"],
        "constraint_check": "PASS",
    })

    with patch("anthropic.AsyncAnthropic", return_value=_mock_haiku(template_payload)):
        with patch("app.agents.template_responder.get_anthropic_api_key", return_value="test-key"):
            response = client.post(f"/gate/{candidate_id}/decide", json={
                "evaluation_id": ev_id,
                "to_email": "cand@example.com",
            })

    assert response.status_code == 200
    data = response.json()
    assert "next_state" in data
    assert "composite" in data
    assert data["next_state"] == "AWAITING_RESUBMISSION"


def test_gate_override_valid():
    candidate_id = "cand-gate-override"
    asyncio.get_event_loop().run_until_complete(
        _store_evaluation(candidate_id, composite=7.5)
    )
    response = client.post(f"/gate/{candidate_id}/override", json={
        "target_state": "WARM_HOLD",
        "reviewer": "founder",
        "reason": "Not a fit at this time.",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["target_state"] == "WARM_HOLD"
    assert data["reviewer"] == "founder"


def test_gate_override_invalid_state():
    response = client.post("/gate/cand-x/override", json={
        "target_state": "INVALID_STATE",
        "reviewer": "founder",
    })
    assert response.status_code == 400


def test_gate_resubmit_task_not_found():
    response = client.post("/gate/cand-x/resubmit", json={
        "task_id": "nonexistent",
        "submission_sha": "abc123",
        "source_code": "def f(): pass",
        "to_email": "x@example.com",
    })
    assert response.status_code == 404


def test_gate_resubmit_success():
    candidate_id = "cand-gate-resubmit"
    task = asyncio.get_event_loop().run_until_complete(_store_task(candidate_id))
    asyncio.get_event_loop().run_until_complete(
        _store_evaluation(candidate_id, composite=7.0, round_num=1)
    )

    with patch("anthropic.AsyncAnthropic", return_value=_mock_opus(_valid_eval_payload(8.0))):
        with patch("app.agents.evaluation_agent.get_anthropic_api_key", return_value="test-key"):
            response = client.post(f"/gate/{candidate_id}/resubmit", json={
                "task_id": task.id,
                "submission_sha": "newsha456",
                "source_code": "# improved solution",
                "to_email": "cand@example.com",
            })

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "resubmission_evaluated"
    assert data["round"] == 2
    assert "composite" in data
