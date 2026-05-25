import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.agents.reply_classifier import ReplyClassifierAgent
from app.schemas import ReplyClassifierOutput

from tests.conftest import TEST_AUTH
client = TestClient(app, headers=TEST_AUTH)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["milestone"].startswith("M")


def test_intake_endpoint():
    with patch("app.api.candidates.FSMEngine") as MockFSM:
        mock_fsm = MockFSM.return_value
        mock_fsm.transition = AsyncMock(return_value=True)

        response = client.post("/candidates/intake", json={
            "name": "Alice Smith",
            "email": "alice@example.com",
            "github_handle": "alicesmith",
            "source": "founder_added",
        })

    assert response.status_code == 200
    data = response.json()
    assert "candidate_id" in data
    assert data["state"] == "ENGAGED"


def test_intake_invalid_email():
    response = client.post("/candidates/intake", json={
        "name": "Bob",
        "email": "not-an-email",
    })
    # CandidateModel validator raises, caught as 422 or 500
    assert response.status_code in (422, 500)


def test_webhook_endpoint_accepted():
    with patch("app.services.gmail_service.GmailService") as MockSvc:
        mock_svc = MockSvc.return_value
        mock_svc.handle_webhook = AsyncMock()

        response = client.post("/candidates/webhook", json={
            "message": {"data": "dGVzdA==", "messageId": "123"},
            "subscription": "projects/test/subscriptions/gmail-sub",
        })

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_approve_endpoint():
    response = client.post("/candidates/approve", json={
        "candidate_id": "cand-uuid-123",
        "approved": True,
        "reviewer": "founder",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["approved"] is True


# ---------------------------------------------------------------------------
# Classifier integration (mocked Claude API)
# ---------------------------------------------------------------------------

def _mock_anthropic_client(response_text: str) -> MagicMock:
    text_block = MagicMock()
    text_block.text = response_text

    mock_response = MagicMock()
    mock_response.content = [text_block]
    mock_response.usage.input_tokens = 60
    mock_response.usage.output_tokens = 25

    mock_instance = MagicMock()
    mock_instance.messages.create = AsyncMock(return_value=mock_response)
    return mock_instance


@pytest.mark.asyncio
async def test_high_confidence_classification():
    payload = json.dumps({
        "intent": "INTERESTED",
        "confidence": 0.95,
        "extracted": {"questions": [], "submission_url": None},
        "summary": "Clear interest expressed",
    })
    from unittest.mock import AsyncMock
    from app.services.llm_client import LLMResponse
    with patch("app.agents.reply_classifier.call_llm",
               new=AsyncMock(return_value=LLMResponse(text=payload, input_tokens=50, output_tokens=20))):
        result = await ReplyClassifierAgent.classify_email("I am interested.", "Cand1")

    assert result.intent == "INTERESTED"
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_schema_failure_fallback():
    from unittest.mock import AsyncMock
    from app.services.llm_client import LLMResponse
    with patch("app.agents.reply_classifier.call_llm",
               new=AsyncMock(return_value=LLMResponse(text="Not a json", input_tokens=50, output_tokens=20))):
        result = await ReplyClassifierAgent.classify_email("Bad response.", "Cand1", retries=1)

    assert result.intent == "OTHER"
    assert result.confidence == 0.0
