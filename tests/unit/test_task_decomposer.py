import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.agents.task_decomposer import TaskDecomposerAgent, validate_no_blocklist_terms, get_pattern
from app.schemas import TaskDecomposerOutput, HeldOutTest, InternalTaskSpec
from app.services.task_store import TaskStore
from app.models import TaskModel

from tests.conftest import TEST_AUTH
client = TestClient(app, headers=TEST_AUTH)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_output(blocklist_check: str = "PASS", success: bool = True) -> str:
    return json.dumps({
        "success": success,
        "corpus_pattern_selected": "rate_limiter",
        "abstraction_verified": True,
        "blocklist_check": blocklist_check,
        "candidate_brief": (
            "## Engineering Problem\n\n"
            "Implement a distributed rate limiter using the token bucket algorithm. "
            "Your solution must be thread-safe and handle concurrent requests.\n\n"
            "### Deliverables\n"
            "- A Python module with a `RateLimiter` class\n"
            "- Unit tests covering core scenarios\n\n"
            "### Submission\n"
            "Reply with your GitHub repository link when complete."
        ),
        "internal_spec": {
            "expected_behavior": "Correct token bucket implementation with thread safety",
            "held_out_tests": [
                {"test_id": "t1", "input": "10 requests in 1 second, limit=5/s", "expected_output": "5 allowed, 5 rejected"},
                {"test_id": "t2", "input": "1 request after 2-second pause", "expected_output": "allowed (tokens refilled)"},
                {"test_id": "t3", "input": "concurrent 100 requests, limit=10/s", "expected_output": "exactly 10 allowed"},
            ],
            "failure_modes": [
                "Race condition in token decrement",
                "Token count goes negative",
                "Clock skew causes incorrect refill rate",
            ],
        },
    })


def _mock_client(response_text: str) -> MagicMock:
    text_block = MagicMock()
    text_block.text = response_text
    mock_response = MagicMock()
    mock_response.content = [text_block]
    mock_response.usage.input_tokens = 300
    mock_response.usage.output_tokens = 800
    mock_instance = MagicMock()
    mock_instance.messages.create = AsyncMock(return_value=mock_response)
    return mock_instance


# ---------------------------------------------------------------------------
# TaskDecomposerAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decomposer_success():
    with patch("anthropic.AsyncAnthropic", return_value=_mock_client(_make_valid_output())):
        with patch("app.agents.task_decomposer.get_anthropic_api_key", return_value="test-key"):
            result = await TaskDecomposerAgent.decompose("software engineer", "senior")

    assert result.success is True
    assert result.blocklist_check == "PASS"
    assert result.corpus_pattern_selected == "rate_limiter"
    assert result.internal_spec is not None
    assert len(result.internal_spec.held_out_tests) == 3


@pytest.mark.asyncio
async def test_decomposer_blocklist_fail_closes():
    with patch("anthropic.AsyncAnthropic", return_value=_mock_client(_make_valid_output(blocklist_check="FAIL"))):
        with patch("app.agents.task_decomposer.get_anthropic_api_key", return_value="test-key"):
            result = await TaskDecomposerAgent.decompose("software engineer", "senior")

    assert result.success is False
    assert result.blocklist_check == "FAIL"
    assert result.candidate_brief == ""


@pytest.mark.asyncio
async def test_decomposer_blocklist_ambiguous_closes():
    with patch("anthropic.AsyncAnthropic", return_value=_mock_client(_make_valid_output(blocklist_check="AMBIGUOUS"))):
        with patch("app.agents.task_decomposer.get_anthropic_api_key", return_value="test-key"):
            result = await TaskDecomposerAgent.decompose("software engineer", "senior")

    assert result.success is False


@pytest.mark.asyncio
async def test_decomposer_schema_failure_returns_safe_default():
    with patch("anthropic.AsyncAnthropic", return_value=_mock_client("not valid json at all")):
        with patch("app.agents.task_decomposer.get_anthropic_api_key", return_value="test-key"):
            result = await TaskDecomposerAgent.decompose("software engineer", "senior", retries=1)

    assert result.success is False
    assert result.blocklist_check == "FAIL"


@pytest.mark.asyncio
async def test_decomposer_rate_limit_propagates():
    import anthropic as _anthropic
    mock_instance = MagicMock()
    mock_instance.messages.create = AsyncMock(side_effect=_anthropic.RateLimitError(
        message="rate limit", response=MagicMock(status_code=429, headers={}), body={}
    ))
    with patch("anthropic.AsyncAnthropic", return_value=mock_instance):
        with patch("app.agents.task_decomposer.get_anthropic_api_key", return_value="test-key"):
            with pytest.raises(_anthropic.RateLimitError):
                await TaskDecomposerAgent.decompose("software engineer", "senior")


# ---------------------------------------------------------------------------
# validate_no_blocklist_terms
# ---------------------------------------------------------------------------

def test_validate_clean_brief_passes():
    clean = "Implement a rate limiter using the token bucket algorithm."
    assert validate_no_blocklist_terms(clean) == []


def test_validate_detects_blocklist_term():
    dirty = "Build a system that analyzes biomarker data from patients."
    violations = validate_no_blocklist_terms(dirty)
    assert "biomarker" in violations


def test_validate_case_insensitive():
    dirty = "Analyze Longevity metrics across user cohorts."
    violations = validate_no_blocklist_terms(dirty)
    assert "longevity" in violations


# ---------------------------------------------------------------------------
# get_pattern
# ---------------------------------------------------------------------------

def test_get_pattern_known():
    pattern = get_pattern("stream_processor")
    assert pattern is not None
    assert pattern.id == "stream_processor"


def test_get_pattern_unknown():
    assert get_pattern("nonexistent") is None


# ---------------------------------------------------------------------------
# TaskStore
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_task_store_add_and_retrieve():
    task = TaskModel(
        candidate_id="cand-store-1",
        candidate_brief="Build a rate limiter.",
        internal_spec={"expected_behavior": "correct", "held_out_tests": [], "failure_modes": []},
        corpus_ref="rate_limiter",
    )
    task_id = await TaskStore.add(task)

    by_id = await TaskStore.get_by_id(task_id)
    assert by_id is not None
    assert by_id.candidate_id == "cand-store-1"

    by_candidate = await TaskStore.get_by_candidate("cand-store-1")
    assert by_candidate is not None
    assert by_candidate.id == task_id


@pytest.mark.asyncio
async def test_task_store_update_repo_url():
    task = TaskModel(
        candidate_id="cand-store-2",
        candidate_brief="Build a cache.",
        internal_spec={},
        corpus_ref="cache_invalidation",
    )
    task_id = await TaskStore.add(task)

    updated = await TaskStore.update_repo_url(task_id, "https://github.com/org/repo")
    assert updated is not None
    assert updated.repo_url == "https://github.com/org/repo"

    fetched = await TaskStore.get_by_id(task_id)
    assert fetched is not None
    assert fetched.repo_url == "https://github.com/org/repo"


@pytest.mark.asyncio
async def test_task_store_get_nonexistent():
    assert await TaskStore.get_by_id("nonexistent-task") is None
    assert await TaskStore.get_by_candidate("nonexistent-candidate") is None


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

def test_health_endpoint_m4():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["milestone"].startswith("M")


def test_generate_task_success():
    with patch("app.agents.task_decomposer.get_anthropic_api_key", return_value="test-key"):
        with patch("anthropic.AsyncAnthropic", return_value=_mock_client(_make_valid_output())):
            response = client.post("/tasks/generate", json={
                "candidate_id": "cand-api-1",
                "candidate_role": "software engineer",
                "candidate_level": "senior",
            })

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generated"
    assert "task_id" in data
    assert "brief_preview" in data


def test_generate_task_blocklist_rejected():
    with patch("app.agents.task_decomposer.get_anthropic_api_key", return_value="test-key"):
        with patch("anthropic.AsyncAnthropic", return_value=_mock_client(
            _make_valid_output(blocklist_check="FAIL", success=False)
        )):
            response = client.post("/tasks/generate", json={
                "candidate_id": "cand-api-blocked",
                "candidate_role": "software engineer",
                "candidate_level": "senior",
            })

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "task_rejected"


def test_get_task_not_found():
    response = client.get("/tasks/nonexistent-task-id")
    assert response.status_code == 404


def test_get_task_hides_internal_spec():
    with patch("app.agents.task_decomposer.get_anthropic_api_key", return_value="test-key"):
        with patch("anthropic.AsyncAnthropic", return_value=_mock_client(_make_valid_output())):
            gen = client.post("/tasks/generate", json={
                "candidate_id": "cand-api-hidden",
                "candidate_role": "software engineer",
                "candidate_level": "senior",
            })

    task_id = gen.json()["task_id"]
    response = client.get(f"/tasks/{task_id}")
    assert response.status_code == 200
    data = response.json()
    assert "internal_spec" not in data
    assert "candidate_brief" in data


def test_provision_repo_not_found():
    response = client.post("/tasks/nonexistent/provision-repo", json={"candidate_id": "x"})
    assert response.status_code == 404


def test_provision_repo_success():
    with patch("app.agents.task_decomposer.get_anthropic_api_key", return_value="test-key"):
        with patch("anthropic.AsyncAnthropic", return_value=_mock_client(_make_valid_output())):
            gen = client.post("/tasks/generate", json={
                "candidate_id": "cand-repo-test",
                "candidate_role": "software engineer",
                "candidate_level": "senior",
            })

    task_id = gen.json()["task_id"]

    with patch("app.services.github_service.GithubService") as MockGH:
        mock_svc = MockGH.return_value
        mock_svc.provision_repo = AsyncMock(return_value="https://github.com/org/candidate-repo")

        response = client.post(f"/tasks/{task_id}/provision-repo", json={
            "candidate_id": "cand-repo-test"
        })

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "provisioned"
    assert "repo_url" in data


def test_send_brief_not_found():
    response = client.post("/tasks/nonexistent/send-brief", json={
        "candidate_id": "x",
        "to_email": "x@example.com",
    })
    assert response.status_code == 404


def test_corpus_has_five_patterns():
    from config.corpus import PATTERNS
    assert len(PATTERNS) == 5


def test_blocklist_not_empty():
    from config.blocklist import BLOCKED_TOPICS
    assert len(BLOCKED_TOPICS) > 0
    assert "longevity" in BLOCKED_TOPICS
