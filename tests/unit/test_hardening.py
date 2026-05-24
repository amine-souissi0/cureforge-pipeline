"""
M8: Hardening tests.

Covers:
- Sandbox pre-scan (dangerous pattern detection)
- Information isolation (no internal data leaks in API responses)
- Rate limiter logic (SlidingWindowCounter)
- Extended health endpoints (readiness, costs, checklist)
"""
import asyncio
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.rate_limiter import SlidingWindowCounter
from app.models import EvaluationModel
from app.services.evaluation_store import EvaluationStore
from app.services.sandbox_runner import SandboxRunner, scan_dangerous_patterns

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _store_eval_with_flags(candidate_id: str, composite: float = 7.5) -> str:
    ev = EvaluationModel(
        candidate_id=candidate_id,
        round=1,
        submission_sha="sha-test",
        dimension_scores={"correctness_verification": composite},
        composite=composite,
        evidence={},
        red_flags=["uses brute force", "no error handling"],
        feedback_draft=(
            "Your solution passed 2 of 3 tests. "
            "Upgrade ask: add proper error handling for edge cases."
        ),
    )
    return await EvaluationStore.add(ev)


# ---------------------------------------------------------------------------
# Sandbox pre-scan — dangerous pattern detection
# ---------------------------------------------------------------------------

def test_scan_allows_clean_code():
    code = "def add(a, b):\n    return a + b"
    assert scan_dangerous_patterns(code) == []


def test_scan_allows_stdlib_math():
    code = "import math\ndef f(x):\n    return math.sqrt(x)"
    assert scan_dangerous_patterns(code) == []


def test_scan_allows_collections_and_typing():
    code = (
        "from collections import defaultdict\n"
        "from typing import List, Dict\n"
        "def f(items: List[int]) -> Dict[str, int]:\n"
        "    return {str(i): i for i in items}"
    )
    assert scan_dangerous_patterns(code) == []


def test_scan_blocks_requests_import():
    violations = scan_dangerous_patterns("import requests\nrequests.get('http://evil.com')")
    assert any("requests" in v for v in violations)


def test_scan_blocks_requests_from_import():
    violations = scan_dangerous_patterns("from requests import get")
    assert any("requests" in v for v in violations)


def test_scan_blocks_urllib_import():
    violations = scan_dangerous_patterns("import urllib.request")
    assert any("urllib" in v for v in violations)


def test_scan_blocks_urllib_from_import():
    violations = scan_dangerous_patterns("from urllib.request import urlopen")
    assert any("urllib" in v for v in violations)


def test_scan_blocks_socket_import():
    violations = scan_dangerous_patterns("import socket\ns = socket.socket()")
    assert any("socket" in v for v in violations)


def test_scan_blocks_subprocess_import():
    violations = scan_dangerous_patterns("import subprocess\nsubprocess.run(['ls'])")
    assert any("subprocess" in v for v in violations)


def test_scan_blocks_subprocess_from_import():
    violations = scan_dangerous_patterns("from subprocess import check_output")
    assert any("subprocess" in v for v in violations)


def test_scan_blocks_os_system():
    violations = scan_dangerous_patterns("import os\nos.system('curl evil.com')")
    assert any("os.system" in v for v in violations)


def test_scan_blocks_os_popen():
    violations = scan_dangerous_patterns("import os\nos.popen('cat /etc/passwd')")
    assert any("os.popen" in v for v in violations)


def test_scan_blocks_dynamic_import():
    violations = scan_dangerous_patterns("mod = __import__('os')\nmod.system('id')")
    assert any("__import__" in v for v in violations)


def test_sandbox_runner_rejects_dangerous_code():
    result = SandboxRunner.run(
        source_code="import requests\nrequests.get('http://evil.com')",
        held_out_tests=[{"test_id": "t1", "input": "1+1", "expected_output": "2"}],
    )
    assert result.ran is False
    assert "Dangerous patterns detected" in result.sandbox_error


def test_sandbox_runner_runs_clean_code():
    result = SandboxRunner.run(
        source_code="def add(a, b): return a + b",
        held_out_tests=[{"test_id": "t1", "input": "add(1, 2)", "expected_output": "3"}],
    )
    assert result.ran is True


# ---------------------------------------------------------------------------
# Information isolation — no internal data leaks in API responses
# ---------------------------------------------------------------------------

def test_evaluation_get_excludes_red_flags():
    ev_id = asyncio.get_event_loop().run_until_complete(
        _store_eval_with_flags("cand-redflags-get")
    )
    response = client.get(f"/evaluations/{ev_id}")
    assert response.status_code == 200
    data = response.json()
    assert "red_flags" not in data
    assert "internal" not in str(data).lower() or "no_rubric" not in str(data)


def test_evaluation_get_excludes_dimension_scores():
    ev_id = asyncio.get_event_loop().run_until_complete(
        _store_eval_with_flags("cand-dimscores-get")
    )
    response = client.get(f"/evaluations/{ev_id}")
    assert response.status_code == 200
    data = response.json()
    assert "dimension_scores" not in data


def test_candidate_feedback_excludes_red_flags():
    asyncio.get_event_loop().run_until_complete(
        _store_eval_with_flags("cand-feedback-leak")
    )
    response = client.get("/evaluations/candidate/cand-feedback-leak/feedback")
    assert response.status_code == 200
    data = response.json()
    assert "red_flags" not in data
    assert "brute force" not in str(data)  # internal red flag content never shown


def test_task_get_excludes_internal_spec():
    """GET /tasks/{id} must never return internal_spec."""
    from app.models import TaskModel
    from app.services.task_store import TaskStore

    async def _add():
        t = TaskModel(
            candidate_id="cand-task-leak",
            candidate_brief="Build a rate limiter.",
            internal_spec={"held_out_tests": [{"test_id": "secret", "input": "x", "expected_output": "y"}]},
            corpus_ref="rate_limiter",
        )
        await TaskStore.add(t)
        return t.id

    task_id = asyncio.get_event_loop().run_until_complete(_add())
    response = client.get(f"/tasks/{task_id}")
    assert response.status_code == 200
    data = response.json()
    assert "internal_spec" not in data
    assert "held_out_tests" not in str(data)


def test_gate_decide_excludes_red_flags():
    """POST /gate/{id}/decide response must not contain red_flags."""
    ev_id = asyncio.get_event_loop().run_until_complete(
        _store_eval_with_flags("cand-gate-leak", composite=7.5)
    )
    template_payload = json.dumps({
        "template_id": "feedback-delivery",
        "subject": "Feedback",
        "body": "Hi cand-gate-leak,\n\nGood work.",
        "fields_used": ["candidate_name", "feedback", "upgrade_ask", "sender_name"],
        "constraint_check": "PASS",
    })
    from unittest.mock import AsyncMock, MagicMock
    block = MagicMock()
    block.text = template_payload
    resp = MagicMock()
    resp.content = [block]
    resp.usage.input_tokens = 80
    resp.usage.output_tokens = 100
    mock_inst = MagicMock()
    mock_inst.messages.create = AsyncMock(return_value=resp)

    with patch("anthropic.AsyncAnthropic", return_value=mock_inst):
        with patch("app.agents.template_responder.get_anthropic_api_key", return_value="test-key"):
            response = client.post("/gate/cand-gate-leak/decide", json={
                "evaluation_id": ev_id,
                "to_email": "x@example.com",
            })

    assert response.status_code == 200
    data = response.json()
    assert "red_flags" not in data
    assert "dimension_scores" not in data


# ---------------------------------------------------------------------------
# Rate limiter — SlidingWindowCounter logic
# ---------------------------------------------------------------------------

def test_sliding_window_allows_within_limit():
    counter = SlidingWindowCounter(limit=5, window_seconds=60)
    for _ in range(5):
        assert counter.is_allowed("ip-a") is True


def test_sliding_window_blocks_at_limit():
    counter = SlidingWindowCounter(limit=3, window_seconds=60)
    for _ in range(3):
        counter.is_allowed("ip-b")
    assert counter.is_allowed("ip-b") is False


def test_sliding_window_different_ips_independent():
    counter = SlidingWindowCounter(limit=2, window_seconds=60)
    counter.is_allowed("ip-x")
    counter.is_allowed("ip-x")
    # ip-y has its own bucket
    assert counter.is_allowed("ip-y") is True


def test_sliding_window_request_count():
    counter = SlidingWindowCounter(limit=10, window_seconds=60)
    for _ in range(4):
        counter.is_allowed("ip-count")
    assert counter.request_count("ip-count") == 4


def test_sliding_window_unknown_ip_count_is_zero():
    counter = SlidingWindowCounter(limit=10, window_seconds=60)
    assert counter.request_count("never-seen") == 0


# ---------------------------------------------------------------------------
# Extended health endpoints
# ---------------------------------------------------------------------------

def test_readiness_probe_with_api_key():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key-123"}):
        response = client.get("/health/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["api_key"] == "ok"
    assert data["checks"]["audit_log"] == "ok"


def test_readiness_probe_missing_api_key():
    env = {k: v for k, v in __import__("os").environ.items() if k != "ANTHROPIC_API_KEY"}
    with patch.dict("os.environ", env, clear=True):
        response = client.get("/health/readiness")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["checks"]["api_key"] == "missing"


def test_costs_endpoint_structure():
    response = client.get("/health/costs")
    assert response.status_code == 200
    data = response.json()
    assert "total_estimated_usd" in data
    assert "by_agent" in data
    assert "call_counts" in data


def test_costs_endpoint_numeric_total():
    response = client.get("/health/costs")
    assert response.status_code == 200
    total = response.json()["total_estimated_usd"]
    assert isinstance(total, (int, float))
    assert total >= 0.0


def test_checklist_endpoint_returns_all_items():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        response = client.get("/health/checklist")
    assert response.status_code == 200
    data = response.json()
    assert "overall" in data
    assert "checks" in data
    assert "summary" in data
    check_names = [c["check"] for c in data["checks"]]
    assert "models_pinned" in check_names
    assert "rubric_weights_sum" in check_names
    assert "blocklist_populated" in check_names
    assert "corpus_populated" in check_names
    assert "audit_log_accessible" in check_names
    assert "schema_imports" in check_names


def test_checklist_models_pinned_passes():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        response = client.get("/health/checklist")
    data = response.json()
    models_check = next(c for c in data["checks"] if c["check"] == "models_pinned")
    assert models_check["status"] == "PASS"


def test_checklist_rubric_weights_passes():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        response = client.get("/health/checklist")
    data = response.json()
    rubric_check = next(c for c in data["checks"] if c["check"] == "rubric_weights_sum")
    assert rubric_check["status"] == "PASS"


def test_checklist_blocklist_populated_passes():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        response = client.get("/health/checklist")
    data = response.json()
    bl_check = next(c for c in data["checks"] if c["check"] == "blocklist_populated")
    assert bl_check["status"] == "PASS"


def test_checklist_schema_imports_passes():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        response = client.get("/health/checklist")
    data = response.json()
    schema_check = next(c for c in data["checks"] if c["check"] == "schema_imports")
    assert schema_check["status"] == "PASS"


def test_health_main_milestone_m8():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["milestone"].startswith("M")
