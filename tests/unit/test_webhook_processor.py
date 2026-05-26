"""
Tests for the Gmail webhook processing pipeline.

All Gmail API and Claude API calls are mocked.
Tests cover: candidate lookup, each routing branch, unknown sender, and the
webhook endpoint itself (Pub/Sub decoding → task enqueue).
"""
import base64
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.fsm import CandidateState
from app.models import CandidateModel, TaskModel
from app.schemas import Message, ReplyClassifierOutput
from app.services.candidate_store import CandidateStore
from app.services.task_store import TaskStore
from app.services.webhook_processor import process_inbound_message

from tests.conftest import TEST_AUTH

client = TestClient(app, headers=TEST_AUTH)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_message(
    sender_email: str = "alice@example.com",
    subject: str = "Re: Engineering Role",
    body: str = "I'm very interested!",
    message_id: str = "gmail-msg-001",
) -> Message:
    return Message(
        id="msg-uuid",
        sender_email=sender_email,
        subject=subject,
        body=body,
        message_id=message_id,
    )


def _mock_classifier(intent: str, confidence: float = 0.95, url: str | None = None) -> MagicMock:
    output = ReplyClassifierOutput(
        intent=intent,
        confidence=confidence,
        extracted={"submission_url": url} if url else {},
        summary=f"test:{intent}",
    )
    mock = AsyncMock(return_value=output)
    return mock


async def _add_candidate(name: str, email: str, state: CandidateState = CandidateState.ENGAGED) -> CandidateModel:
    c = CandidateModel(name=name, email=email, state=state)
    await CandidateStore.add(c)
    return c


# ---------------------------------------------------------------------------
# Unknown sender — skip silently
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_sender_skipped():
    msg = _make_message(sender_email="nobody@unknown.com")
    result = await process_inbound_message(msg)
    assert result.startswith("unknown_sender:")


# ---------------------------------------------------------------------------
# DECLINE routing → FSM WITHDRAWN
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decline_transitions_to_withdrawn():
    candidate = await _add_candidate("Bob Decline", "bob-decline@example.com")

    with patch(
        "app.agents.reply_classifier.ReplyClassifierAgent.classify_email",
        _mock_classifier("DECLINE"),
    ):
        result = await process_inbound_message(_make_message(sender_email=candidate.email))

    assert "DECLINE" in result

    updated = await CandidateStore.get_by_id(candidate.id)
    assert updated is not None
    assert updated.state == CandidateState.WITHDRAWN


# ---------------------------------------------------------------------------
# TASK_SUBMISSION routing → store repo URL + queue acknowledgment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submission_stores_repo_url():
    candidate = await _add_candidate(
        "Carol Submit", "carol-submit@example.com", CandidateState.AWAITING_SUBMISSION
    )
    task = TaskModel(
        candidate_id=candidate.id,
        candidate_brief="Build a rate limiter.",
        internal_spec={},
        corpus_ref="rate_limiter",
    )
    await TaskStore.add(task)

    submission_url = "https://github.com/carol/rate-limiter"

    mock_eval_task = MagicMock()
    mock_eval_task.delay = MagicMock()

    with patch(
        "app.agents.reply_classifier.ReplyClassifierAgent.classify_email",
        _mock_classifier("TASK_SUBMISSION", url=submission_url),
    ), patch(
        "app.api.candidates.run_submission_evaluation",
        mock_eval_task,
    ):
        result = await process_inbound_message(
            _make_message(sender_email=candidate.email)
        )

    assert "TASK_SUBMISSION" in result

    updated_task = await TaskStore.get_by_candidate(candidate.id)
    assert updated_task is not None
    assert updated_task.repo_url == submission_url


# ---------------------------------------------------------------------------
# INTERESTED routing → acknowledgment draft queued
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_interested_queues_acknowledgment_draft():
    from app.services.approval_queue import ApprovalQueue
    from app.services.send_policy import SendMode

    candidate = await _add_candidate("Dave Interested", "dave-interested@example.com")

    with patch(
        "app.agents.reply_classifier.ReplyClassifierAgent.classify_email",
        _mock_classifier("INTERESTED"),
    ):
        with patch("app.services.send_policy.get_send_mode", return_value=SendMode.DRAFT):
            with patch("app.api.candidates.generate_task_for_candidate") as mock_gen:
                mock_gen.delay = MagicMock()
                result = await process_inbound_message(
                    _make_message(sender_email=candidate.email)
                )

    assert "INTERESTED" in result
    pending = await ApprovalQueue.list_pending()
    candidate_drafts = [d for d in pending if d.candidate_id == candidate.id]
    assert len(candidate_drafts) >= 1
    assert candidate_drafts[0].template_id == "acknowledgment"


# ---------------------------------------------------------------------------
# QUESTION routing → answer-common-question draft queued
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_question_queues_answer_draft():
    from app.schemas import TemplateResponderOutput
    from app.services.approval_queue import ApprovalQueue
    from app.services.send_policy import SendMode

    candidate = await _add_candidate("Eve Question", "eve-question@example.com")

    mock_render = AsyncMock(return_value=TemplateResponderOutput(
        template_id="answer-common-question",
        subject="Re: What stack do you use?",
        body="Hi Eve, we use Python 3.11...",
        fields_used=["candidate_name", "sender_name"],
        constraint_check="PASS",
    ))

    with patch(
        "app.agents.reply_classifier.ReplyClassifierAgent.classify_email",
        _mock_classifier("QUESTION"),
    ):
        with patch("app.agents.template_responder.TemplateResponderAgent.render", mock_render):
            with patch("app.services.send_policy.get_send_mode", return_value=SendMode.DRAFT):
                result = await process_inbound_message(
                    _make_message(sender_email=candidate.email, body="What stack do you use?")
                )

    assert "QUESTION" in result
    pending = await ApprovalQueue.list_pending()
    candidate_drafts = [d for d in pending if d.candidate_id == candidate.id]
    assert len(candidate_drafts) >= 1
    assert candidate_drafts[0].template_id == "answer-common-question"


# ---------------------------------------------------------------------------
# Low-confidence → human review (no automated action)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_low_confidence_routes_to_human_review():
    from app.services.approval_queue import ApprovalQueue

    candidate = await _add_candidate("Frank Ambiguous", "frank-ambiguous@example.com")
    before_count = len(await ApprovalQueue.list_pending())

    with patch(
        "app.agents.reply_classifier.ReplyClassifierAgent.classify_email",
        _mock_classifier("OTHER", confidence=0.40),
    ):
        result = await process_inbound_message(
            _make_message(sender_email=candidate.email, body="Maybe. Not sure.")
        )

    assert "OTHER" in result
    # No new drafts created for human_review
    after_count = len(await ApprovalQueue.list_pending())
    assert after_count == before_count


# ---------------------------------------------------------------------------
# Webhook endpoint — Pub/Sub decoding + Celery task enqueue
# ---------------------------------------------------------------------------

def _make_pubsub_payload(history_id: str = "98765", email: str = "alice@example.com") -> dict:
    notification = json.dumps({"emailAddress": email, "historyId": history_id})
    encoded = base64.urlsafe_b64encode(notification.encode()).decode()
    return {
        "message": {"data": encoded, "messageId": "pubsub-msg-1"},
        "subscription": "projects/test/subscriptions/gmail-sub",
    }


def test_webhook_endpoint_accepts_valid_pubsub():
    with patch("app.api.candidates.process_email_task") as mock_task:
        mock_task.delay = MagicMock()
        response = client.post("/candidates/webhook", json=_make_pubsub_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    mock_task.delay.assert_called_once_with("98765")


def test_webhook_endpoint_empty_data_accepted():
    """Empty data field is silently dropped — not an error."""
    with patch("app.api.candidates.process_email_task") as mock_task:
        mock_task.delay = MagicMock()
        response = client.post("/candidates/webhook", json={
            "message": {"data": "", "messageId": "x"},
            "subscription": "projects/test/subscriptions/gmail-sub",
        })

    assert response.status_code == 200
    mock_task.delay.assert_not_called()


def test_webhook_endpoint_missing_history_id():
    """Notification without historyId is dropped gracefully."""
    notification = json.dumps({"emailAddress": "alice@example.com"})
    encoded = base64.urlsafe_b64encode(notification.encode()).decode()

    with patch("app.api.candidates.process_email_task") as mock_task:
        mock_task.delay = MagicMock()
        response = client.post("/candidates/webhook", json={
            "message": {"data": encoded, "messageId": "x"},
            "subscription": "projects/test/subscriptions/gmail-sub",
        })

    assert response.status_code == 200
    mock_task.delay.assert_not_called()
