import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.templates import TemplateRegistry, MissingFieldError, _substitute
from app.agents.template_responder import TemplateResponderAgent, _render_direct
from app.services.approval_queue import ApprovalQueue, DraftEmail
from app.services.send_policy import SendMode, get_send_mode, set_candidate_mode
from app.schemas import TemplateResponderOutput

from tests.conftest import TEST_AUTH
client = TestClient(app, headers=TEST_AUTH)


# ---------------------------------------------------------------------------
# _substitute (renderer utility)
# ---------------------------------------------------------------------------

def test_substitute_fills_all_placeholders():
    result = _substitute("Hi {name}, your round is {round}.", {"name": "Alice", "round": "2"})
    assert result == "Hi Alice, your round is 2."


def test_substitute_leaves_unknown_placeholders():
    result = _substitute("Hello {name} and {unknown}.", {"name": "Bob"})
    assert result == "Hello Bob and {unknown}."


# ---------------------------------------------------------------------------
# TemplateRegistry
# ---------------------------------------------------------------------------

def test_registry_lists_all_six_templates():
    ids = TemplateRegistry.list_templates()
    expected = {
        "acknowledgment",
        "answer-common-question",
        "task-assignment-cover",
        "feedback-delivery",
        "warm-hold",
        "offer-cover",
    }
    assert expected == set(ids)


def test_registry_render_acknowledgment():
    subject, body = TemplateRegistry.render("acknowledgment", {
        "candidate_name": "Alice",
        "original_subject": "Inquiry",
        "sender_name": "CureForge Team",
    })
    assert "Alice" in body
    assert "Inquiry" in subject
    assert "CureForge Team" in body


def test_registry_render_missing_field_raises():
    with pytest.raises(MissingFieldError):
        TemplateRegistry.render("acknowledgment", {
            "candidate_name": "Alice",
            # original_subject and sender_name missing
        })


def test_registry_unknown_template_raises():
    with pytest.raises(KeyError):
        TemplateRegistry.get("nonexistent-template")


def test_no_deadline_language_in_templates():
    """Constraint: no timeline language in base templates."""
    forbidden = ["within 7 days", "asap", "immediately", "by friday", "deadline"]
    from config.templates import TEMPLATES
    for tmpl in TEMPLATES.values():
        body_lower = tmpl.body_template.lower()
        for phrase in forbidden:
            assert phrase not in body_lower, (
                f"Template {tmpl.id!r} contains forbidden phrase: {phrase!r}"
            )


def test_no_rubric_language_in_templates():
    """Constraint: no rubric/scoring language in candidate-facing templates."""
    forbidden = ["rubric", "dimension", "weight", "composite", "score"]
    from config.templates import TEMPLATES
    for tmpl in TEMPLATES.values():
        body_lower = tmpl.body_template.lower()
        for phrase in forbidden:
            assert phrase not in body_lower, (
                f"Template {tmpl.id!r} contains forbidden phrase: {phrase!r}"
            )


# ---------------------------------------------------------------------------
# _render_direct (deterministic rendering for acknowledgment)
# ---------------------------------------------------------------------------

def test_render_direct_acknowledgment():
    result = _render_direct("acknowledgment", {
        "candidate_name": "Bob",
        "original_subject": "Hello",
        "sender_name": "Team",
    })
    assert result.constraint_check == "PASS"
    assert "Bob" in result.body
    assert result.template_id == "acknowledgment"


# ---------------------------------------------------------------------------
# TemplateResponderAgent — acknowledgment bypasses LLM
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_acknowledgment_renders_without_api_call():
    with patch("app.agents.template_responder.get_anthropic_api_key", return_value="test-key"):
        result = await TemplateResponderAgent.render(
            template_id="acknowledgment",
            candidate_context={
                "candidate_name": "Carol",
                "original_subject": "Role inquiry",
                "sender_name": "CureForge",
            },
        )
    assert result.constraint_check == "PASS"
    assert "Carol" in result.body


@pytest.mark.asyncio
async def test_template_responder_success():
    payload = json.dumps({
        "template_id": "answer-common-question",
        "subject": "Re: Your Questions",
        "body": "Hi Dave,\n\nWe use Python 3.11.\n\nBest,\nCureForge",
        "fields_used": ["candidate_name", "answer", "sender_name"],
        "constraint_check": "PASS",
    })

    text_block = MagicMock()
    text_block.text = payload
    mock_response = MagicMock()
    mock_response.content = [text_block]
    mock_response.usage.input_tokens = 80
    mock_response.usage.output_tokens = 40

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        with patch("app.agents.template_responder.get_anthropic_api_key", return_value="test-key"):
            result = await TemplateResponderAgent.render(
                template_id="answer-common-question",
                candidate_context={"candidate_name": "Dave", "sender_name": "CureForge"},
                extra_context={"answer": "We use Python 3.11."},
            )

    assert result.constraint_check == "PASS"
    assert result.template_id == "answer-common-question"


@pytest.mark.asyncio
async def test_template_responder_constraint_fail_logged():
    payload = json.dumps({
        "template_id": "feedback-delivery",
        "subject": "Feedback",
        "body": "Rubric score: 8/10.",
        "fields_used": ["candidate_name"],
        "constraint_check": "FAIL",
    })

    text_block = MagicMock()
    text_block.text = payload
    mock_response = MagicMock()
    mock_response.content = [text_block]
    mock_response.usage.input_tokens = 60
    mock_response.usage.output_tokens = 30

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        with patch("app.agents.template_responder.get_anthropic_api_key", return_value="test-key"):
            result = await TemplateResponderAgent.render(
                template_id="feedback-delivery",
                candidate_context={"candidate_name": "Eve"},
            )

    assert result.constraint_check == "FAIL"


@pytest.mark.asyncio
async def test_template_responder_unknown_template_raises():
    with pytest.raises(KeyError):
        await TemplateResponderAgent.render(
            template_id="nonexistent",
            candidate_context={"candidate_name": "X"},
        )


# ---------------------------------------------------------------------------
# ApprovalQueue
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approval_queue_add_and_list():
    draft = DraftEmail(
        candidate_id="cand-1",
        template_id="warm-hold",
        subject="Staying in Touch",
        body="Hi Alice...",
        to_email="alice@example.com",
    )
    draft_id = await ApprovalQueue.add(draft)
    pending = await ApprovalQueue.list_pending()
    ids = [d.draft_id for d in pending]
    assert draft_id in ids


@pytest.mark.asyncio
async def test_approval_queue_approve():
    draft = DraftEmail(
        candidate_id="cand-2",
        template_id="acknowledgment",
        subject="Re: Hi",
        body="Hi Bob...",
        to_email="bob@example.com",
    )
    draft_id = await ApprovalQueue.add(draft)
    approved = await ApprovalQueue.approve(draft_id, "founder")
    assert approved is not None
    assert approved.status == "approved"
    assert approved.reviewed_by == "founder"


@pytest.mark.asyncio
async def test_approval_queue_reject():
    draft = DraftEmail(
        candidate_id="cand-3",
        template_id="warm-hold",
        subject="Hold",
        body="Hi Carol...",
        to_email="carol@example.com",
    )
    draft_id = await ApprovalQueue.add(draft)
    rejected = await ApprovalQueue.reject(draft_id, "founder")
    assert rejected is not None
    assert rejected.status == "rejected"


@pytest.mark.asyncio
async def test_approval_queue_get_nonexistent():
    result = await ApprovalQueue.get("nonexistent-draft-id")
    assert result is None


# ---------------------------------------------------------------------------
# SendPolicy
# ---------------------------------------------------------------------------

def test_send_policy_acknowledgment_auto():
    mode = get_send_mode("cand-x", "acknowledgment")
    assert mode == SendMode.AUTO


def test_send_policy_task_assignment_draft():
    mode = get_send_mode("cand-x", "task-assignment-cover")
    assert mode == SendMode.DRAFT


def test_send_policy_candidate_override():
    set_candidate_mode("cand-override", SendMode.AUTO)
    mode = get_send_mode("cand-override", "task-assignment-cover")
    assert mode == SendMode.AUTO


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

def test_list_templates_endpoint():
    response = client.get("/templates")
    assert response.status_code == 200
    data = response.json()
    assert "acknowledgment" in data["templates"]
    assert len(data["templates"]) == 6


def test_list_drafts_endpoint():
    response = client.get("/templates/drafts")
    assert response.status_code == 200
    assert "drafts" in response.json()


def test_reject_nonexistent_draft():
    response = client.post(
        "/templates/drafts/bad-id/reject",
        json={"reviewer": "founder"},
    )
    assert response.status_code == 404


def test_approve_nonexistent_draft():
    response = client.post(
        "/templates/drafts/bad-id/approve",
        json={"reviewer": "founder"},
    )
    assert response.status_code == 404


def test_send_unknown_template_returns_404():
    with patch("app.agents.template_responder.get_anthropic_api_key", return_value="test-key"):
        response = client.post("/templates/send", json={
            "candidate_id": "cand-1",
            "template_id": "nonexistent",
            "to_email": "test@example.com",
            "candidate_context": {"candidate_name": "Test"},
        })
    assert response.status_code == 404


def test_send_acknowledgment_drafts_because_no_gmail():
    """Acknowledgment is AUTO but GmailService fails without credentials — verifies policy wiring."""
    with patch("app.agents.template_responder.get_anthropic_api_key", return_value="test-key"):
        with patch("app.services.gmail_service.GmailService") as MockGmail:
            mock_svc = MockGmail.return_value
            mock_svc.send_email = AsyncMock(return_value="gmail-msg-id-123")

            response = client.post("/templates/send", json={
                "candidate_id": "cand-ack",
                "template_id": "acknowledgment",
                "to_email": "candidate@example.com",
                "candidate_context": {
                    "candidate_name": "Frank",
                    "original_subject": "Hello",
                    "sender_name": "CureForge",
                },
            })

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "sent"
    assert data["gmail_id"] == "gmail-msg-id-123"


def test_health_endpoint_m3():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["milestone"].startswith("M")
