"""
M10: API key authentication tests.

Verifies that protected routes enforce X-API-Key and that exempt routes
(health, oauth) remain accessible without credentials.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

_authed = TestClient(app, headers={"X-API-Key": "test-api-key"})
_no_key = TestClient(app)
_wrong_key = TestClient(app, headers={"X-API-Key": "wrong-key"})


# ---------------------------------------------------------------------------
# Protected routes — must reject unauthenticated requests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("post", "/candidates/intake"),
    ("get",  "/templates"),
    ("get",  "/templates/drafts"),
    ("get",  "/tasks/some-id"),
    ("get",  "/evaluations/some-id"),
    ("get",  "/gate/some-id/status"),
    ("get",  "/dashboard/pipeline"),
])
def test_missing_key_returns_401(method: str, path: str):
    response = getattr(_no_key, method)(path)
    assert response.status_code == 401, f"{method.upper()} {path} should require auth"


@pytest.mark.parametrize("method,path", [
    ("post", "/candidates/intake"),
    ("get",  "/templates"),
    ("get",  "/dashboard/pipeline"),
])
def test_wrong_key_returns_403(method: str, path: str):
    response = getattr(_wrong_key, method)(path)
    assert response.status_code == 403, f"{method.upper()} {path} should reject wrong key"


# ---------------------------------------------------------------------------
# Exempt routes — must remain accessible without credentials
# ---------------------------------------------------------------------------

def test_health_liveness_no_auth():
    response = _no_key.get("/health")
    assert response.status_code == 200


def test_health_readiness_no_auth():
    response = _no_key.get("/health/readiness")
    # May return 503 if API_KEY check fails, but not 401/403
    assert response.status_code != 401
    assert response.status_code != 403


def test_health_checklist_no_auth():
    response = _no_key.get("/health/checklist")
    assert response.status_code != 401
    assert response.status_code != 403


def test_health_costs_no_auth():
    response = _no_key.get("/health/costs")
    assert response.status_code != 401
    assert response.status_code != 403


# ---------------------------------------------------------------------------
# Valid key passes through to normal business logic
# ---------------------------------------------------------------------------

def test_valid_key_reaches_endpoint():
    # /templates should return 200 (list of templates) not 401/403
    response = _authed.get("/templates")
    assert response.status_code == 200
