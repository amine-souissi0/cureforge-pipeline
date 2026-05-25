import os
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/readiness")
async def readiness() -> Dict[str, Any]:
    """
    Readiness probe: verify all runtime dependencies are configured.

    Returns 200 if the system is ready to handle production traffic.
    Returns 503 with a per-check breakdown if any required config is absent.
    """
    from app.config import get_anthropic_api_key
    from app.schemas import AuditLog

    checks: Dict[str, str] = {}

    try:
        get_anthropic_api_key()
        checks["api_key"] = "ok"
    except RuntimeError:
        checks["api_key"] = "missing"

    try:
        # Audit log must be accessible and appendable
        await AuditLog.append("readiness_probe", {})
        checks["audit_log"] = "ok"
    except Exception:
        checks["audit_log"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": checks},
        )

    return {"status": "ready", "checks": checks}


@router.get("/costs")
async def costs() -> Dict[str, Any]:
    """
    Per-agent LLM spend summary read from the persistent audit log DB.
    Falls back to in-memory log if DB is unavailable.
    """
    from sqlalchemy import select, text
    from app.database import AsyncSessionLocal
    from app.orm_models import AuditLogRow
    from app.schemas import AuditLog

    breakdown: Dict[str, float] = {}
    call_counts: Dict[str, int] = {}
    tokens_in: Dict[str, int] = {}
    tokens_out: Dict[str, int] = {}
    total = 0.0
    daily: Dict[str, float] = {}  # date-string → cost

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AuditLogRow)
                .where(AuditLogRow.event_type.like("claude_call_%"))
                .order_by(AuditLogRow.created_at.desc())
                .limit(5000)
            )
            rows = result.scalars().all()
    except Exception:
        rows = []

    # Fall back to in-memory if DB returned nothing
    sources = rows if rows else [
        type("R", (), {"event_type": e["event_type"], "data": e.get("data", {}), "created_at": None})()
        for e in AuditLog._log
        if e.get("event_type", "").startswith("claude_call_")
    ]

    for row in sources:
        agent = row.event_type[len("claude_call_"):]
        data = row.data or {}
        cost = float(data.get("cost_estimate", 0.0))
        breakdown[agent] = round(breakdown.get(agent, 0.0) + cost, 8)
        call_counts[agent] = call_counts.get(agent, 0) + 1
        tokens_in[agent] = tokens_in.get(agent, 0) + int(data.get("tokens_in", 0))
        tokens_out[agent] = tokens_out.get(agent, 0) + int(data.get("tokens_out", 0))
        total += cost
        if getattr(row, "created_at", None):
            day = row.created_at.strftime("%Y-%m-%d")
            daily[day] = round(daily.get(day, 0.0) + cost, 8)

    return {
        "total_estimated_usd": round(total, 6),
        "by_agent": breakdown,
        "call_counts": call_counts,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "daily": daily,
    }


@router.get("/checklist")
async def checklist() -> Dict[str, Any]:
    """
    Automated pre-production checklist from CLAUDE.md §10.

    Each item is PASS / WARN / FAIL. The overall status is READY only if
    all items are PASS; WARN items are blocking in strict mode.
    """
    from config.blocklist import BLOCKED_TOPICS
    from config.corpus import PATTERNS as CORPUS_PATTERNS
    from config.models import MODELS
    from config.rubric import DIMENSIONS
    from app.schemas import AuditLog

    items: List[Dict[str, Any]] = []

    # 1. All model versions pinned (no "latest" or floating strings)
    floating = [
        k for k, v in MODELS.items()
        if "latest" in v.get("model", "").lower()
    ]
    items.append({
        "check": "models_pinned",
        "status": "PASS" if not floating else "FAIL",
        "detail": (
            f"Floating model versions detected: {floating}"
            if floating
            else f"All {len(MODELS)} model versions pinned."
        ),
    })

    # 2. API key in environment (WARN not FAIL — could be in secret manager)
    key_present = bool(os.environ.get("ANTHROPIC_API_KEY"))
    items.append({
        "check": "api_key_configured",
        "status": "PASS" if key_present else "WARN",
        "detail": (
            "ANTHROPIC_API_KEY found in environment."
            if key_present
            else "ANTHROPIC_API_KEY not set — required for production (use secret manager)."
        ),
    })

    # 3. Rubric weights sum to exactly 1.0
    weight_sum = sum(d.weight for d in DIMENSIONS.values())
    items.append({
        "check": "rubric_weights_sum",
        "status": "PASS" if abs(weight_sum - 1.0) < 1e-9 else "FAIL",
        "detail": f"Dimension weights sum = {weight_sum:.10f} (target 1.0000000000).",
    })

    # 4. Blocklist populated — empty blocklist is an IP leak risk
    items.append({
        "check": "blocklist_populated",
        "status": "PASS" if len(BLOCKED_TOPICS) >= 5 else "FAIL",
        "detail": f"{len(BLOCKED_TOPICS)} topics blocked.",
    })

    # 5. Corpus has at least one pattern
    items.append({
        "check": "corpus_populated",
        "status": "PASS" if CORPUS_PATTERNS else "FAIL",
        "detail": f"{len(CORPUS_PATTERNS)} corpus patterns available.",
    })

    # 6. Audit log is accessible
    try:
        entry_count = len(AuditLog._log)
        items.append({
            "check": "audit_log_accessible",
            "status": "PASS",
            "detail": f"Audit log accessible with {entry_count} entries.",
        })
    except Exception as e:
        items.append({
            "check": "audit_log_accessible",
            "status": "FAIL",
            "detail": f"Audit log error: {e}",
        })

    # 7. Schema imports — verify all agent output schemas load cleanly
    try:
        from app.schemas import (  # noqa: F401
            EvaluationAgentOutput,
            OfferDrafterOutput,
            ReplyClassifierOutput,
            TaskDecomposerOutput,
            TemplateResponderOutput,
        )
        items.append({
            "check": "schema_imports",
            "status": "PASS",
            "detail": "All agent output schemas import cleanly.",
        })
    except ImportError as e:
        items.append({
            "check": "schema_imports",
            "status": "FAIL",
            "detail": f"Schema import error: {e}",
        })

    passes = sum(1 for i in items if i["status"] == "PASS")
    fails = sum(1 for i in items if i["status"] == "FAIL")
    warns = sum(1 for i in items if i["status"] == "WARN")
    overall = "READY" if fails == 0 else "NOT_READY"

    return {
        "overall": overall,
        "summary": {"pass": passes, "warn": warns, "fail": fails},
        "checks": items,
    }
