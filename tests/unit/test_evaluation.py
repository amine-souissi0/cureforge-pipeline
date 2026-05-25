import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.agents.evaluation_agent import EvaluationAgent, _validate_no_rubric_leak, get_dimension_ids
from app.services.sandbox_runner import SandboxRunner, SandboxResult
from app.services.evaluation_store import EvaluationStore
from app.services.llm_client import LLMResponse
from app.models import EvaluationModel
from config.rubric import compute_composite, HIRE_THRESHOLD, RESUBMIT_THRESHOLD, DIMENSIONS

from tests.conftest import TEST_AUTH
client = TestClient(app, headers=TEST_AUTH)


def _llm(text: str) -> AsyncMock:
    return AsyncMock(return_value=LLMResponse(text=text, input_tokens=500, output_tokens=600))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_agent_payload(composite: float = 8.0) -> str:
    return json.dumps({
        "dimension_scores": {
            "correctness_verification": 8.5,
            "invariant_failclosed_discipline": 8.0,
            "structure_determinism": 7.5,
            "testing_instrumentation": 8.0,
            "communication_iteration": 7.0,
        },
        "composite": composite,
        "evidence_summary": "Strong solution. Token bucket is correctly implemented with thread safety.",
        "red_flags": ["Minor: no backpressure handling"],
        "candidate_feedback_draft": (
            "Your solution passed 3 of 4 tests. The concurrent scenario (test t3) "
            "revealed a race condition in the token decrement logic — two threads decremented "
            "simultaneously, allowing one extra request through. "
            "Upgrade ask: add a unit test that explicitly verifies thread safety under concurrent load."
        ),
    })




def _make_sandbox_result(passed: int = 3, total: int = 4) -> SandboxResult:
    from app.services.sandbox_runner import TestResult
    results = []
    for i in range(total):
        results.append(TestResult(
            test_id=f"t{i+1}",
            passed=i < passed,
            stdout="ok" if i < passed else "wrong",
            stderr="",
            execution_ms=12.5,
        ))
    return SandboxResult(
        ran=True,
        test_results=results,
        total_tests=total,
        passed_tests=passed,
        failed_tests=total - passed,
    )


# ---------------------------------------------------------------------------
# config/rubric.py
# ---------------------------------------------------------------------------

def test_rubric_weights_sum_to_one():
    total = sum(d.weight for d in DIMENSIONS.values())
    assert abs(total - 1.0) < 1e-9


def test_compute_composite_perfect():
    scores = {d: 10.0 for d in DIMENSIONS}
    assert compute_composite(scores) == 10.0


def test_compute_composite_zero():
    scores = {d: 0.0 for d in DIMENSIONS}
    assert compute_composite(scores) == 0.0


def test_compute_composite_weighted():
    scores = {
        "correctness_verification": 10.0,
        "invariant_failclosed_discipline": 0.0,
        "structure_determinism": 0.0,
        "testing_instrumentation": 0.0,
        "communication_iteration": 0.0,
    }
    # Only correctness_verification (weight=0.30) contributed
    assert compute_composite(scores) == round(10.0 * 0.30, 2)


def test_hire_threshold_constant():
    assert HIRE_THRESHOLD == 8.5


def test_resubmit_threshold_constant():
    assert RESUBMIT_THRESHOLD == 7.0


# ---------------------------------------------------------------------------
# SandboxRunner
# ---------------------------------------------------------------------------

def test_sandbox_passes_correct_code():
    source = "def add(a, b): return a + b"
    tests = [{"test_id": "t1", "input": "add(2, 3)", "expected_output": "5"}]
    result = SandboxRunner.run(source, tests)
    assert result.ran is True
    assert result.passed_tests == 1
    assert result.failed_tests == 0
    assert result.pass_rate == 1.0


def test_sandbox_fails_wrong_output():
    source = "def add(a, b): return a - b"
    tests = [{"test_id": "t1", "input": "add(2, 3)", "expected_output": "5"}]
    result = SandboxRunner.run(source, tests)
    assert result.passed_tests == 0
    assert result.failed_tests == 1


def test_sandbox_handles_multiple_tests():
    source = "def mul(a, b): return a * b"
    tests = [
        {"test_id": "t1", "input": "mul(2, 3)", "expected_output": "6"},
        {"test_id": "t2", "input": "mul(0, 99)", "expected_output": "0"},
        {"test_id": "t3", "input": "mul(-1, 5)", "expected_output": "-5"},
    ]
    result = SandboxRunner.run(source, tests)
    assert result.passed_tests == 3
    assert result.pass_rate == 1.0


def test_sandbox_handles_runtime_error():
    source = "def div(a, b): return a / b"
    tests = [{"test_id": "t1", "input": "div(1, 0)", "expected_output": "error"}]
    result = SandboxRunner.run(source, tests)
    assert result.ran is True
    assert result.passed_tests == 0


def test_sandbox_times_out():
    source = "import time\ndef slow(): time.sleep(999)"
    tests = [{"test_id": "t1", "input": "slow()", "expected_output": "done"}]
    result = SandboxRunner.run(source, tests, timeout=1)
    assert result.ran is True
    assert result.test_results[0].passed is False
    assert "Timed out" in result.test_results[0].error


def test_sandbox_empty_source():
    result = SandboxRunner.run("", [{"test_id": "t1", "input": "1+1", "expected_output": "2"}])
    assert result.ran is False
    assert result.sandbox_error != ""


def test_sandbox_pass_rate_calculation():
    result = _make_sandbox_result(passed=3, total=4)
    assert result.pass_rate == 0.75


# ---------------------------------------------------------------------------
# EvaluationAgent — mocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluation_agent_success():
    sandbox = _make_sandbox_result(3, 4)
    with patch("app.agents.evaluation_agent.call_llm", new=_llm(_valid_agent_payload(7.9))):
        result = await EvaluationAgent.evaluate(
            source_code="def f(): pass",
            sandbox_result=sandbox,
            internal_spec={"expected_behavior": "correct", "held_out_tests": [], "failure_modes": []},
        )

    assert result.composite > 0
    assert len(result.dimension_scores) == 5
    assert result.candidate_feedback_draft != ""


@pytest.mark.asyncio
async def test_evaluation_agent_composite_recomputed():
    """Model returns composite=9.9 but dimension_scores only support ~8.0 — system recomputes."""
    sandbox = _make_sandbox_result(3, 4)
    with patch("app.agents.evaluation_agent.call_llm", new=_llm(_valid_agent_payload(9.9))):
        result = await EvaluationAgent.evaluate(
            source_code="def f(): pass",
            sandbox_result=sandbox,
            internal_spec={},
        )

    expected = compute_composite({
        "correctness_verification": 8.5,
        "invariant_failclosed_discipline": 8.0,
        "structure_determinism": 7.5,
        "testing_instrumentation": 8.0,
        "communication_iteration": 7.0,
    })
    assert result.composite == expected


@pytest.mark.asyncio
async def test_evaluation_agent_rubric_leak_raises():
    leaky = json.dumps({
        "dimension_scores": {d: 7.0 for d in get_dimension_ids()},
        "composite": 7.0,
        "evidence_summary": "ok",
        "red_flags": [],
        "candidate_feedback_draft": "Your correctness_verification dimension score was low.",
    })
    sandbox = _make_sandbox_result(1, 4)
    with patch("app.agents.evaluation_agent.call_llm", new=_llm(leaky)):
        with pytest.raises(RuntimeError):
            await EvaluationAgent.evaluate("def f(): pass", sandbox, {})


def test_validate_no_rubric_leak_clean():
    _validate_no_rubric_leak("Your solution passed 3 of 4 tests. Please add thread safety.")


def test_validate_no_rubric_leak_detects_term():
    with pytest.raises(ValueError, match="rubric"):
        _validate_no_rubric_leak("Your rubric score was high.")


# ---------------------------------------------------------------------------
# EvaluationStore
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluation_store_add_and_retrieve():
    ev = EvaluationModel(
        candidate_id="cand-ev-1",
        round=1,
        submission_sha="abc123",
        dimension_scores={"correctness_verification": 8.0},
        composite=8.0,
        evidence={},
        feedback_draft="Good work.",
    )
    ev_id = await EvaluationStore.add(ev)
    fetched = await EvaluationStore.get_by_id(ev_id)
    assert fetched is not None
    assert fetched.composite == 8.0


@pytest.mark.asyncio
async def test_evaluation_store_multi_round():
    for i in range(3):
        ev = EvaluationModel(
            candidate_id="cand-ev-multi",
            round=i + 1,
            submission_sha=f"sha{i}",
            dimension_scores={},
            composite=float(7 + i),
            evidence={},
            feedback_draft="Feedback.",
        )
        await EvaluationStore.add(ev)

    all_evals = await EvaluationStore.list_by_candidate("cand-ev-multi")
    assert len(all_evals) == 3
    latest = await EvaluationStore.get_latest_by_candidate("cand-ev-multi")
    assert latest is not None
    assert latest.round == 3


@pytest.mark.asyncio
async def test_evaluation_store_nonexistent():
    assert await EvaluationStore.get_by_id("nonexistent") is None
    assert await EvaluationStore.get_latest_by_candidate("nonexistent") is None


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

def test_health_endpoint_m5():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["milestone"].startswith("M")


def test_get_evaluation_not_found():
    response = client.get("/evaluations/nonexistent")
    assert response.status_code == 404


def test_list_candidate_evaluations_empty():
    response = client.get("/evaluations/candidate/nobody")
    assert response.status_code == 200
    assert response.json()["total_rounds"] == 0


def test_get_candidate_feedback_not_found():
    response = client.get("/evaluations/candidate/nobody/feedback")
    assert response.status_code == 404


def test_submit_evaluation_task_not_found():
    response = client.post("/evaluations/submit", json={
        "candidate_id": "cand-1",
        "submission_sha": "abc123",
        "source_code": "def f(): pass",
        "task_id": "nonexistent-task",
    })
    assert response.status_code == 404


def test_submit_evaluation_success():
    from app.models import TaskModel
    from app.services.task_store import TaskStore
    import asyncio

    task = TaskModel(
        candidate_id="cand-submit-test",
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
    asyncio.get_event_loop().run_until_complete(TaskStore.add(task))

    with patch("app.agents.evaluation_agent.call_llm", new=_llm(_valid_agent_payload(8.0))):
        response = client.post("/evaluations/submit", json={
            "candidate_id": "cand-submit-test",
            "submission_sha": "deadbeef",
            "source_code": "# correct solution",
            "task_id": task.id,
        })

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "evaluation_complete"
    assert "evaluation_id" in data
    assert "composite" in data


def test_get_evaluation_hides_red_flags():
    """Verify red_flags and dimension_scores are not in the API response."""
    import asyncio
    evals = asyncio.get_event_loop().run_until_complete(
        EvaluationStore.list_by_candidate("cand-submit-test")
    )
    if not evals:
        return
    ev_id = evals[-1].id
    response = client.get(f"/evaluations/{ev_id}")
    assert response.status_code == 200
    data = response.json()
    assert "red_flags" not in data
    assert "dimension_scores" not in data
    assert "candidate_feedback" in data
