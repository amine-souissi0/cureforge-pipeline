"""Tests for orchestrator.router.dispatch."""

from unittest.mock import patch

import pytest

from models.database import AgentSession
from orchestrator.router import DispatchError, dispatch


def test_dispatch_grant_discover():
    with patch("orchestrator.router.discover_grants", return_value=[{"opportunity_id": "1"}]):
        out = dispatch("grant.discover", {"keywords": "aging", "limit": 3}, db=None)
    assert out == {"opportunities": [{"opportunity_id": "1"}]}


def test_dispatch_grant_reporter():
    with patch("orchestrator.router.search_nih_reporter", return_value=[{"project_num": "R01"}]):
        out = dispatch("grant.reporter", {"keywords": "aging"}, db=None)
    assert len(out["projects"]) == 1


def test_dispatch_grant_draft_single():
    with patch("orchestrator.router.draft_narrative", return_value="narrative text"):
        out = dispatch(
            "grant.draft",
            {
                "opportunity": {"title": "T"},
                "project_info": {
                    "title": "x",
                    "hypothesis": "h",
                    "approach": "a",
                    "innovation": "i",
                    "team": "t",
                    "preliminary_data": "p",
                },
            },
            db=None,
        )
    assert out["narrative"] == "narrative text"


def test_dispatch_unknown_task():
    with pytest.raises(DispatchError):
        dispatch("unknown.task", {}, db=None)


def test_dispatch_persists_agent_session(db_session):
    with patch("orchestrator.router.discover_grants", return_value=[]):
        dispatch(
            "grant.discover",
            {"keywords": "k", "limit": 2, "session_id": "sess-orchestrator-1"},
            db=db_session,
        )
    row = db_session.query(AgentSession).filter_by(session_id="sess-orchestrator-1").one()
    assert row.status == "completed"
    assert "opportunities" in (row.result_json or "")
