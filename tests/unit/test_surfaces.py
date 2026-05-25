import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.fsm import CandidateState
from app.models import CandidateModel, EvaluationModel
from app.schemas import OfferDrafterOutput
from app.services.candidate_store import CandidateStore
from app.services.evaluation_store import EvaluationStore
from app.services.approval_queue import ApprovalQueue, DraftEmail
from app.services.llm_client import LLMResponse

from tests.conftest import TEST_AUTH
client = TestClient(app, headers=TEST_AUTH)


def _llm(text: str) -> AsyncMock:
    return AsyncMock(return_value=LLMResponse(text=text, input_tokens=200, output_tokens=300))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _add_candidate(name: str = "Alice", email_suffix: str = "") -> CandidateModel:
    suffix = email_suffix or name.lower().replace(" ", "")
    c = CandidateModel(
        name=name,
        email=f"{suffix}@example.com",
        state=CandidateState.HIRE_RECOMMENDED,
    )
    await CandidateStore.add(c)
    return c


async def _add_evaluation(candidate_id: str, composite: float, round_num: int = 1) -> str:
    ev = EvaluationModel(
        candidate_id=candidate_id,
        round=round_num,
        submission_sha=f"sha-{round_num}",
        dimension_scores={"correctness_verification": composite},
        composite=composite,
        evidence={},
        feedback_draft="Good submission. Upgrade ask: add error handling.",
    )
    return await EvaluationStore.add(ev)


def _valid_offer_payload() -> str:
    return json.dumps({
        "role": "Staff Engineer",
        "offer_details": (
            "We're pleased to offer you the Staff Engineer position.\n\n"
            "Compensation: $200,000 base salary.\n"
            "Equity: 0.5% options vesting over 4 years.\n"
            "Benefits: Full health, dental, vision."
        ),
        "compensation_summary": "$200k base, 0.5% equity, standard benefits",
        "constraint_check": "PASS",
    })




# ---------------------------------------------------------------------------
# OfferDrafterOutput schema
# ---------------------------------------------------------------------------

def test_offer_drafter_output_valid():
    o = OfferDrafterOutput(
        role="Staff Engineer",
        offer_details="We'd like to extend an offer...",
        compensation_summary="$180k + equity",
        constraint_check="PASS",
    )
    assert o.role == "Staff Engineer"
    assert o.constraint_check == "PASS"


def test_offer_drafter_output_fail_constraint():
    o = OfferDrafterOutput(
        role="Staff Engineer",
        offer_details="Respond by Friday.",
        compensation_summary="$180k",
        constraint_check="FAIL",
    )
    assert o.constraint_check == "FAIL"


def test_offer_drafter_output_rejects_extra_fields():
    # OfferDrafterOutput should only accept defined fields
    o = OfferDrafterOutput(
        role="SWE",
        offer_details="...",
        compensation_summary="...",
        constraint_check="PASS",
    )
    assert not hasattr(o, "timeline")


# ---------------------------------------------------------------------------
# OfferDrafterAgent — mocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_offer_drafter_agent_success():
    from app.agents.offer_drafter import OfferDrafterAgent

    with patch("app.agents.offer_drafter.call_llm", new=_llm(_valid_offer_payload())):
        result = await OfferDrafterAgent.draft(
            candidate_name="Alice",
            role="Staff Engineer",
            compensation="$200,000 base",
            equity="0.5% options",
        )

    assert result.constraint_check == "PASS"
    assert result.role == "Staff Engineer"
    assert "200,000" in result.offer_details


@pytest.mark.asyncio
async def test_offer_drafter_agent_schema_failure_raises():
    from app.agents.offer_drafter import OfferDrafterAgent

    with patch("app.agents.offer_drafter.call_llm", new=_llm("not valid json at all")):
        with pytest.raises(RuntimeError, match="OfferDrafter failed"):
            await OfferDrafterAgent.draft(
                candidate_name="Bob",
                role="Engineer",
                compensation="$150k",
                retries=1,
            )


@pytest.mark.asyncio
async def test_offer_drafter_agent_constraint_fail_returned():
    """Agent returns FAIL constraint check — should still return the object (not raise)."""
    from app.agents.offer_drafter import OfferDrafterAgent

    fail_payload = json.dumps({
        "role": "Staff Engineer",
        "offer_details": "You must respond by Friday.",
        "compensation_summary": "$180k",
        "constraint_check": "FAIL",
    })

    with patch("app.agents.offer_drafter.call_llm", new=_llm(fail_payload)):
        result = await OfferDrafterAgent.draft(
            candidate_name="Carol",
            role="Staff Engineer",
            compensation="$180k",
        )

    assert result.constraint_check == "FAIL"


# ---------------------------------------------------------------------------
# CandidateStore
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_candidate_store_add_and_get():
    c = await _add_candidate("Dave", "dave-store")
    found = await CandidateStore.get_by_id(c.id)
    assert found is not None
    assert found.name == "Dave"


@pytest.mark.asyncio
async def test_candidate_store_get_by_email():
    c = await _add_candidate("Eve", "eve-store")
    found = await CandidateStore.get_by_email("eve-store@example.com")
    assert found is not None
    assert found.id == c.id


@pytest.mark.asyncio
async def test_candidate_store_list_all_includes_new_candidate():
    before = len(await CandidateStore.list_all())
    await _add_candidate("Frank", "frank-store")
    after = len(await CandidateStore.list_all())
    assert after == before + 1


@pytest.mark.asyncio
async def test_candidate_store_update_state():
    c = await _add_candidate("Grace", "grace-store")
    updated = await CandidateStore.update_state(c.id, CandidateState.HIRED)
    assert updated is not None
    assert updated.state == CandidateState.HIRED


@pytest.mark.asyncio
async def test_candidate_store_count_by_state():
    await _add_candidate("Heidi", "heidi-store")
    counts = await CandidateStore.count_by_state()
    assert isinstance(counts, dict)
    assert "HIRE_RECOMMENDED" in counts


@pytest.mark.asyncio
async def test_candidate_store_unknown_id_returns_none():
    assert await CandidateStore.get_by_id("nonexistent-id") is None


# ---------------------------------------------------------------------------
# Dashboard — /pipeline
# ---------------------------------------------------------------------------

def test_dashboard_pipeline_empty_ish():
    response = client.get("/dashboard/pipeline")
    assert response.status_code == 200
    data = response.json()
    assert "total_candidates" in data
    assert "by_state" in data
    assert "pending_drafts" in data
    assert "candidates" in data


def test_dashboard_pipeline_shows_added_candidate():
    asyncio.get_event_loop().run_until_complete(
        _add_candidate("Ivan", "ivan-pipeline")
    )
    response = client.get("/dashboard/pipeline")
    assert response.status_code == 200
    data = response.json()
    ids = [c["candidate_id"] for c in data["candidates"]]
    candidates_by_name = [c for c in data["candidates"] if c["name"] == "Ivan"]
    assert len(candidates_by_name) >= 1


def test_dashboard_pipeline_candidate_has_composite():
    c = asyncio.get_event_loop().run_until_complete(
        _add_candidate("Judy", "judy-pipeline")
    )
    asyncio.get_event_loop().run_until_complete(
        _add_evaluation(c.id, composite=8.7)
    )
    response = client.get("/dashboard/pipeline")
    data = response.json()
    judy = next((x for x in data["candidates"] if x["candidate_id"] == c.id), None)
    assert judy is not None
    assert judy["latest_composite"] == 8.7
    assert judy["rounds_completed"] == 1


# ---------------------------------------------------------------------------
# Dashboard — /candidate/{id}
# ---------------------------------------------------------------------------

def test_dashboard_candidate_not_found():
    response = client.get("/dashboard/candidate/nonexistent-xyz")
    assert response.status_code == 404


def test_dashboard_candidate_detail_no_evaluations():
    c = asyncio.get_event_loop().run_until_complete(
        _add_candidate("Karl", "karl-detail")
    )
    response = client.get(f"/dashboard/candidate/{c.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["candidate_id"] == c.id
    assert data["rounds_completed"] == 0
    assert data["evaluations"] == []
    assert data["projected_next_state"] is None


def test_dashboard_candidate_detail_with_evaluation():
    c = asyncio.get_event_loop().run_until_complete(
        _add_candidate("Lara", "lara-detail")
    )
    asyncio.get_event_loop().run_until_complete(
        _add_evaluation(c.id, composite=7.5)
    )
    response = client.get(f"/dashboard/candidate/{c.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["rounds_completed"] == 1
    assert data["evaluations"][0]["composite"] == 7.5
    assert data["projected_next_state"] == "AWAITING_RESUBMISSION"


def test_dashboard_candidate_hire_recommended_projected_state():
    c = asyncio.get_event_loop().run_until_complete(
        _add_candidate("Mallory", "mallory-detail")
    )
    asyncio.get_event_loop().run_until_complete(
        _add_evaluation(c.id, composite=9.0)
    )
    response = client.get(f"/dashboard/candidate/{c.id}")
    data = response.json()
    assert data["projected_next_state"] == "HIRE_RECOMMENDED"


# ---------------------------------------------------------------------------
# Dashboard — /drafts
# ---------------------------------------------------------------------------

def test_dashboard_drafts_returns_list():
    response = client.get("/dashboard/drafts")
    assert response.status_code == 200
    data = response.json()
    assert "pending_count" in data
    assert "drafts" in data
    assert isinstance(data["drafts"], list)


def test_dashboard_drafts_shows_queued_draft():
    async def _add_draft():
        draft = DraftEmail(
            candidate_id="cand-draft-test",
            template_id="warm-hold",
            subject="Staying in Touch",
            body="Hi there.",
            to_email="x@example.com",
        )
        return await ApprovalQueue.add(draft)

    asyncio.get_event_loop().run_until_complete(_add_draft())
    response = client.get("/dashboard/drafts")
    data = response.json()
    assert data["pending_count"] >= 1
    template_ids = [d["template_id"] for d in data["drafts"]]
    assert "warm-hold" in template_ids


# ---------------------------------------------------------------------------
# Dashboard — POST /offer/{candidate_id}
# ---------------------------------------------------------------------------

def test_dashboard_offer_candidate_not_found():
    response = client.post("/dashboard/offer/nonexistent", json={
        "role": "Engineer",
        "compensation": "$150k",
        "to_email": "x@example.com",
    })
    assert response.status_code == 404


def test_dashboard_offer_no_evaluation():
    c = asyncio.get_event_loop().run_until_complete(
        _add_candidate("Nina", "nina-offer")
    )
    response = client.post(f"/dashboard/offer/{c.id}", json={
        "role": "Engineer",
        "compensation": "$150k",
        "to_email": "nina@example.com",
    })
    assert response.status_code == 400
    assert "No evaluations" in response.json()["detail"]


def test_dashboard_offer_below_hire_threshold():
    c = asyncio.get_event_loop().run_until_complete(
        _add_candidate("Oscar", "oscar-offer")
    )
    asyncio.get_event_loop().run_until_complete(
        _add_evaluation(c.id, composite=6.0)
    )
    response = client.post(f"/dashboard/offer/{c.id}", json={
        "role": "Engineer",
        "compensation": "$150k",
        "to_email": "oscar@example.com",
    })
    assert response.status_code == 400
    assert "below hire threshold" in response.json()["detail"]


def test_dashboard_offer_success():
    c = asyncio.get_event_loop().run_until_complete(
        _add_candidate("Peggy", "peggy-offer")
    )
    asyncio.get_event_loop().run_until_complete(
        _add_evaluation(c.id, composite=9.0)
    )

    template_payload = json.dumps({
        "template_id": "offer-cover",
        "subject": "An Offer",
        "body": "Hi Peggy,\n\nWe'd like to extend the following offer:\n\nStaff Engineer at $200k.\n\nBest,\nCureForge Team",
        "fields_used": ["candidate_name", "offer_details", "sender_name"],
        "constraint_check": "PASS",
    })

    with patch("app.agents.offer_drafter.call_llm", new=_llm(_valid_offer_payload())):
        with patch("app.agents.template_responder.call_llm", new=_llm(template_payload)):
            response = client.post(f"/dashboard/offer/{c.id}", json={
                "role": "Staff Engineer",
                "compensation": "$200,000 base",
                "equity": "0.5%",
                "to_email": "peggy@example.com",
            })

    assert response.status_code == 200
    data = response.json()
    assert data["candidate_id"] == c.id
    assert data["status"] == "draft_queued_for_approval"
    assert "draft_id" in data
    assert data["role"] == "Staff Engineer"


# ---------------------------------------------------------------------------
# Health check — milestone updated to M7
# ---------------------------------------------------------------------------

def test_health_milestone_m7():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["milestone"].startswith("M")
    assert data["status"] == "ok"
