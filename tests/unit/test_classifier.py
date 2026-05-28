import json
import pytest
from unittest.mock import AsyncMock, patch

from app.agents.reply_classifier import ReplyClassifierAgent, route_classified_email
from app.schemas import ReplyClassifierOutput
from app.services.llm_client import LLMResponse


def _llm(text: str) -> AsyncMock:
    return AsyncMock(return_value=LLMResponse(text=text, input_tokens=50, output_tokens=20))


@pytest.mark.asyncio
async def test_interested_classification():
    payload = json.dumps({
        "intent": "INTERESTED",
        "confidence": 0.95,
        "extracted": {"questions": [], "submission_url": None},
        "summary": "Candidate is interested",
    })
    with patch("app.agents.reply_classifier.call_llm", new=_llm(payload)):
        result = await ReplyClassifierAgent.classify_email("I am interested!", "cand1")

    assert result.intent == "INTERESTED"
    assert result.confidence == 0.95
    assert result.is_high_confidence()


@pytest.mark.asyncio
async def test_task_submission_with_url():
    payload = json.dumps({
        "intent": "TASK_SUBMISSION",
        "confidence": 0.98,
        "extracted": {"questions": [], "submission_url": "https://github.com/user/repo"},
        "summary": "Submitted repo",
    })
    with patch("app.agents.reply_classifier.call_llm", new=_llm(payload)):
        result = await ReplyClassifierAgent.classify_email("Here is my repo: https://github.com/user/repo", "cand1")

    assert result.intent == "TASK_SUBMISSION"
    assert result.extracted is not None
    assert result.extracted["submission_url"] == "https://github.com/user/repo"


@pytest.mark.asyncio
async def test_decline_classification():
    payload = json.dumps({
        "intent": "DECLINE",
        "confidence": 0.92,
        "extracted": {"questions": [], "submission_url": None},
        "summary": "Candidate declined",
    })
    with patch("app.agents.reply_classifier.call_llm", new=_llm(payload)):
        result = await ReplyClassifierAgent.classify_email("Not interested, thanks.", "cand1")

    assert result.intent == "DECLINE"
    assert result.is_high_confidence()


@pytest.mark.asyncio
async def test_low_confidence_is_not_high_confidence():
    payload = json.dumps({
        "intent": "OTHER",
        "confidence": 0.45,
        "extracted": {},
        "summary": "Ambiguous",
    })
    with patch("app.agents.reply_classifier.call_llm", new=_llm(payload)):
        result = await ReplyClassifierAgent.classify_email("Hmm, maybe.", "cand1")

    assert result.intent == "OTHER"
    assert not result.is_high_confidence()


@pytest.mark.asyncio
async def test_schema_failure_returns_other_after_retries():
    with patch("app.agents.reply_classifier.call_llm", new=_llm("not valid json")):
        result = await ReplyClassifierAgent.classify_email("Bad response.", "cand1", retries=1)

    assert result.intent == "OTHER"
    assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Routing logic tests (no API calls needed)
# ---------------------------------------------------------------------------

def test_route_low_confidence_to_human():
    output = ReplyClassifierOutput(intent="OTHER", confidence=0.45)
    assert route_classified_email(output, "cand1") == "human_review"


def test_route_interested_to_template_responder():
    output = ReplyClassifierOutput(intent="INTERESTED", confidence=0.95)
    assert route_classified_email(output, "cand1") == "template_responder:INTERESTED"


def test_route_decline_to_fsm():
    output = ReplyClassifierOutput(intent="DECLINE", confidence=0.90)
    assert route_classified_email(output, "cand1") == "fsm_withdrawn"


def test_route_task_submission_with_url():
    output = ReplyClassifierOutput(
        intent="TASK_SUBMISSION",
        confidence=0.97,
        extracted={"submission_url": "https://github.com/user/repo"},
    )
    assert route_classified_email(output, "cand1") == "submission_intake:https://github.com/user/repo"


def test_route_task_submission_without_url_to_human():
    output = ReplyClassifierOutput(
        intent="TASK_SUBMISSION",
        confidence=0.97,
        extracted={"submission_url": None},
    )
    assert route_classified_email(output, "cand1") == "request_submission_url"


def test_route_question_to_template_responder():
    output = ReplyClassifierOutput(intent="QUESTION", confidence=0.88)
    assert route_classified_email(output, "cand1") == "template_responder:QUESTION"
