"""
Central task dispatch: map task_type + JSON payload to agent entrypoints.

Callers may persist outcomes via models.database.upsert_agent_session_row.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from agents.grant_agent import discover_grants, draft_narrative, draft_narrative_workflow, search_nih_reporter
from models.database import upsert_agent_session_row

logger = logging.getLogger(__name__)


class DispatchError(ValueError):
    """Unknown task type or invalid payload."""

    pass


def dispatch(task_type: str, payload: dict[str, Any], *, db: Optional[Session] = None) -> dict[str, Any]:
    """
    Execute a task synchronously and return a JSON-serializable dict.

    If `db` and payload contain `session_id`, the result is upserted to AgentSession.
    """
    session_id = payload.get("session_id")

    try:
        if task_type == "grant.discover":
            keywords = payload.get("keywords") or ""
            limit = int(payload.get("limit", 10))
            result = {"opportunities": discover_grants(keywords, limit=limit)}
        elif task_type == "grant.reporter":
            keywords = payload.get("keywords") or ""
            limit = int(payload.get("limit", 10))
            result = {"projects": search_nih_reporter(keywords, limit=limit)}
        elif task_type == "grant.draft":
            opp = payload.get("opportunity") or {}
            proj = payload.get("project_info") or {}
            model = payload.get("model")
            use_workflow = bool(payload.get("use_workflow", False))
            include_landscape = bool(payload.get("include_landscape", False))
            if use_workflow:
                wf = draft_narrative_workflow(
                    opp,
                    proj,
                    model=model,
                    include_landscape=include_landscape,
                    landscape_keywords=payload.get("landscape_keywords"),
                )
                result = {"workflow": wf, "narrative": wf["narrative"]}
            else:
                text = draft_narrative(opp, proj, model=model)
                result = {"narrative": text}
        else:
            raise DispatchError(f"unknown task_type: {task_type!r}")
    except DispatchError:
        raise
    except Exception as exc:
        logger.exception("dispatch failed for %s", task_type)
        if db is not None and session_id:
            upsert_agent_session_row(
                db,
                session_id=str(session_id),
                task_type=task_type,
                payload=payload,
                status="failed",
                error_message=str(exc),
            )
            db.commit()
        raise

    if db is not None and session_id:
        upsert_agent_session_row(
            db,
            session_id=str(session_id),
            task_type=task_type,
            payload=payload,
            result=result,
            status="completed",
        )
        db.commit()

    return result
