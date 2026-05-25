"""
M8: End-to-end synthetic candidate journey tests.

These tests simulate full pipeline flows with all Claude API calls mocked.
They verify that each milestone's components integrate correctly end-to-end.

All three happy-path journeys are covered:
  Journey A — intake → evaluate → resubmit path (composite 7.5)
  Journey B — intake → evaluate × 2 → warm hold (composite < 7.0, 2 rounds)
  Journey C — intake → evaluate → hire recommended (composite ≥ 8.5) → offer draft
"""
import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import EvaluationModel
from app.services.evaluation_store import EvaluationStore
from app.services.candidate_store import CandidateStore

from tests.conftest import TEST_AUTH
client = TestClient(app, headers=TEST_AUTH)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@e2e-test.com"


async def _store_evaluation(candidate_id: str, composite: float, round_num: int = 1) -> str:
    ev = EvaluationModel(
        candidate_id=candidate_id,
        round=round_num,
        submission_sha=f"sha-e2e-{round_num}",
        dimension_scores={"correctness_verification": composite},
        composite=composite,
        evidence={},
        red_flags=[],
        feedback_draft=(
            "Your solution passed key tests. "
            "Upgrade ask: add comprehensive error handling."
        ),
    )
    return await EvaluationStore.add(ev)


def _mock_haiku(payload: str) -> MagicMock:
    block = MagicMock()
    block.text = payload
    resp = MagicMock()
    resp.content = [block]
    resp.usage.input_tokens = 80
    resp.usage.output_tokens = 120
    inst = MagicMock()
    inst.messages.create = AsyncMock(return_value=resp)
    return inst


def _feedback_template_payload(candidate_name: str) -> str:
    return json.dumps({
        "template_id": "feedback-delivery",
        "subject": "Feedback on Your Submission",
        "body": f"Hi {candidate_name},\n\nGood work. Upgrade ask: add error handling.",
        "fields_used": ["candidate_name", "feedback", "upgrade_ask", "sender_name"],
        "constraint_check": "PASS",
    })


def _warmhold_template_payload(candidate_name: str) -> str:
    return json.dumps({
        "template_id": "warm-hold",
        "subject": "Staying in Touch",
        "body": f"Hi {candidate_name},\n\nThank you for your time.",
        "fields_used": ["candidate_name", "sender_name"],
        "constraint_check": "PASS",
    })


def _offer_payload() -> str:
    return json.dumps({
        "role": "Staff Engineer",
        "offer_details": "We're excited to offer you the Staff Engineer role at $200k.",
        "compensation_summary": "$200k base, 0.5% equity",
        "constraint_check": "PASS",
    })


def _offer_template_payload(candidate_name: str) -> str:
    return json.dumps({
        "template_id": "offer-cover",
        "subject": "An Offer",
        "body": f"Hi {candidate_name},\n\nWe're excited to extend the following offer:\n\nStaff Engineer at $200k.\n\nBest,\nCureForge Team",
        "fields_used": ["candidate_name", "offer_details", "sender_name"],
        "constraint_check": "PASS",
    })


# ---------------------------------------------------------------------------
# Journey A: intake → evaluate → resubmit path
# ---------------------------------------------------------------------------

def test_journey_a_resubmit_path():
    """
    Composite 7.5 → AWAITING_RESUBMISSION.
    Verifies: intake persists, gate/decide returns correct next_state,
    dashboard reflects the candidate.
    """
    # 1. Intake
    response = client.post("/candidates/intake", json={
        "name": "Journey A",
        "email": _unique_email("journey-a"),
    })
    assert response.status_code == 200
    candidate_id = response.json()["candidate_id"]
    assert candidate_id

    # 2. Store evaluation (7.5 composite — resubmit range)
    ev_id = asyncio.get_event_loop().run_until_complete(
        _store_evaluation(candidate_id, composite=7.5)
    )

    # 3. Gate status shows 1 round
    response = client.get(f"/gate/{candidate_id}/status")
    assert response.status_code == 200
    gate_data = response.json()
    assert gate_data["rounds_completed"] == 1
    assert gate_data["latest_composite"] == 7.5
    assert gate_data["projected_next_state"] == "AWAITING_RESUBMISSION"

    # 4. Gate decide → AWAITING_RESUBMISSION
    feedback_payload = _feedback_template_payload("Journey A")
    with patch("anthropic.AsyncAnthropic", return_value=_mock_haiku(feedback_payload)):
        with patch("app.config.get_anthropic_api_key", return_value="test-key"):
            response = client.post(f"/gate/{candidate_id}/decide", json={
                "evaluation_id": ev_id,
                "to_email": "journey-a@test.com",
            })

    assert response.status_code == 200
    decide_data = response.json()
    assert decide_data["next_state"] == "AWAITING_RESUBMISSION"
    assert decide_data["composite"] == 7.5
    assert decide_data["requires_founder_approval"] is False
    assert "feedback_draft_id" in decide_data

    # 5. Dashboard shows candidate with correct data
    response = client.get(f"/dashboard/candidate/{candidate_id}")
    assert response.status_code == 200
    dash = response.json()
    assert dash["candidate_id"] == candidate_id
    assert dash["rounds_completed"] == 1
    assert len(dash["evaluations"]) == 1
    assert dash["evaluations"][0]["composite"] == 7.5


# ---------------------------------------------------------------------------
# Journey B: intake → evaluate × 2 → warm hold
# ---------------------------------------------------------------------------

def test_journey_b_warm_hold_path():
    """
    Two rounds with composite < 7.0 → WARM_HOLD.
    Verifies: multi-round evaluation history, warm-hold template queued.
    """
    # 1. Intake
    response = client.post("/candidates/intake", json={
        "name": "Journey B",
        "email": _unique_email("journey-b"),
    })
    assert response.status_code == 200
    candidate_id = response.json()["candidate_id"]

    # 2. Store two low-scoring evaluations
    asyncio.get_event_loop().run_until_complete(
        _store_evaluation(candidate_id, composite=5.0, round_num=1)
    )
    ev_id = asyncio.get_event_loop().run_until_complete(
        _store_evaluation(candidate_id, composite=4.5, round_num=2)
    )

    # 3. Gate status shows 2 rounds, projected WARM_HOLD
    response = client.get(f"/gate/{candidate_id}/status")
    assert response.status_code == 200
    gate_data = response.json()
    assert gate_data["rounds_completed"] == 2
    assert gate_data["projected_next_state"] == "WARM_HOLD"

    # 4. Gate decide → WARM_HOLD (two LLM calls: feedback + warm-hold template)
    call_count = 0
    feedback_pl = _feedback_template_payload("Journey B")
    warmhold_pl = _warmhold_template_payload("Journey B")

    async def _mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        payload = feedback_pl if call_count == 1 else warmhold_pl
        block = MagicMock()
        block.text = payload
        resp = MagicMock()
        resp.content = [block]
        resp.usage.input_tokens = 80
        resp.usage.output_tokens = 100
        return resp

    mock_inst = MagicMock()
    mock_inst.messages.create = _mock_create

    with patch("anthropic.AsyncAnthropic", return_value=mock_inst):
        with patch("app.config.get_anthropic_api_key", return_value="test-key"):
            response = client.post(f"/gate/{candidate_id}/decide", json={
                "evaluation_id": ev_id,
                "to_email": "journey-b@test.com",
            })

    assert response.status_code == 200
    decide_data = response.json()
    assert decide_data["next_state"] == "WARM_HOLD"
    assert decide_data["composite"] == 4.5

    # 5. Dashboard reflects both rounds
    response = client.get(f"/dashboard/candidate/{candidate_id}")
    assert response.status_code == 200
    dash = response.json()
    assert dash["rounds_completed"] == 2
    assert len(dash["evaluations"]) == 2


# ---------------------------------------------------------------------------
# Journey C: intake → evaluate → hire recommended → offer draft
# ---------------------------------------------------------------------------

def test_journey_c_hire_recommended_and_offer():
    """
    Composite 9.0 → HIRE_RECOMMENDED → offer draft created.
    Verifies: hire path, offer drafter end-to-end, draft visible in approval queue.
    """
    # 1. Intake
    response = client.post("/candidates/intake", json={
        "name": "Journey C",
        "email": _unique_email("journey-c"),
    })
    assert response.status_code == 200
    candidate_id = response.json()["candidate_id"]

    # 2. Store high-scoring evaluation
    ev_id = asyncio.get_event_loop().run_until_complete(
        _store_evaluation(candidate_id, composite=9.0)
    )

    # 3. Gate status → projected HIRE_RECOMMENDED
    response = client.get(f"/gate/{candidate_id}/status")
    assert response.status_code == 200
    assert response.json()["projected_next_state"] == "HIRE_RECOMMENDED"

    # 4. Gate decide (recommend mode) → HIRE_RECOMMENDED
    feedback_payload = _feedback_template_payload("Journey C")
    with patch("anthropic.AsyncAnthropic", return_value=_mock_haiku(feedback_payload)):
        with patch("app.config.get_anthropic_api_key", return_value="test-key"):
            response = client.post(f"/gate/{candidate_id}/decide", json={
                "evaluation_id": ev_id,
                "to_email": "journey-c@test.com",
                "mode": "recommend",
            })

    assert response.status_code == 200
    decide_data = response.json()
    assert decide_data["next_state"] == "HIRE_RECOMMENDED"
    assert decide_data["requires_founder_approval"] is True

    # 5. Draft offer (mocking OfferDrafter + TemplateResponder)
    offer_pl = _offer_payload()
    tmpl_pl = _offer_template_payload("Journey C")
    call_n = 0

    async def _multi_create(**kwargs):
        nonlocal call_n
        call_n += 1
        payload = offer_pl if call_n == 1 else tmpl_pl
        block = MagicMock()
        block.text = payload
        resp = MagicMock()
        resp.content = [block]
        resp.usage.input_tokens = 200
        resp.usage.output_tokens = 300
        return resp

    mock_inst = MagicMock()
    mock_inst.messages.create = _multi_create

    with patch("anthropic.AsyncAnthropic", return_value=mock_inst):
        with patch("app.config.get_anthropic_api_key", return_value="test-key"):
            with patch("app.config.get_anthropic_api_key", return_value="test-key"):
                response = client.post(f"/dashboard/offer/{candidate_id}", json={
                    "role": "Staff Engineer",
                    "compensation": "$200,000 base",
                    "equity": "0.5%",
                    "to_email": "journey-c@test.com",
                })

    assert response.status_code == 200
    offer_data = response.json()
    assert offer_data["status"] == "draft_queued_for_approval"
    assert offer_data["role"] == "Staff Engineer"
    draft_id = offer_data["draft_id"]
    assert draft_id

    # 6. Draft appears in approval queue
    response = client.get("/dashboard/drafts")
    assert response.status_code == 200
    drafts = response.json()
    draft_ids = [d["draft_id"] for d in drafts["drafts"]]
    assert draft_id in draft_ids

    # 7. Candidate visible in pipeline
    response = client.get("/dashboard/pipeline")
    assert response.status_code == 200
    pipeline = response.json()
    cand_ids = [c["candidate_id"] for c in pipeline["candidates"]]
    assert candidate_id in cand_ids


# ---------------------------------------------------------------------------
# Journey D: gate override (founder force-state)
# ---------------------------------------------------------------------------

def test_journey_d_founder_override():
    """
    Founder can override FSM state to WARM_HOLD regardless of score.
    Verifies: override endpoint, audit trail, response structure.
    """
    # 1. Intake
    response = client.post("/candidates/intake", json={
        "name": "Journey D",
        "email": _unique_email("journey-d"),
    })
    assert response.status_code == 200
    candidate_id = response.json()["candidate_id"]

    # 2. Store an evaluation so the override endpoint can read latest composite
    asyncio.get_event_loop().run_until_complete(
        _store_evaluation(candidate_id, composite=6.0)
    )

    # 3. Founder overrides to WARM_HOLD
    response = client.post(f"/gate/{candidate_id}/override", json={
        "target_state": "WARM_HOLD",
        "reviewer": "founder",
        "reason": "Not a fit for the current role.",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["current_state"] == "WARM_HOLD"
    assert data["reviewer"] == "founder"
    assert "previous_state" in data
