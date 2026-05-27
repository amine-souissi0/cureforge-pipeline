"""§9 — Assemble founder dossier when a candidate reaches HIRE_RECOMMENDED."""
from typing import Any, Dict, List

from app.schemas import AuditLog
from app.services.candidate_store import CandidateStore
from app.services.evaluation_store import EvaluationStore
from app.services.message_store import MessageStore


async def assemble_dossier(candidate_id: str) -> Dict[str, Any]:
    """
    Build a complete hire dossier: all rounds, scores, evidence, message transcript.
    Stored in the audit log and returned for immediate use.
    """
    candidate = await CandidateStore.get_by_id(candidate_id)
    if candidate is None:
        return {}

    evaluations = await EvaluationStore.list_by_candidate(candidate_id)
    messages = await MessageStore.list_by_candidate(candidate_id)

    rounds: List[Dict[str, Any]] = []
    for ev in evaluations:
        rounds.append({
            "round": ev.round,
            "submission_sha": ev.submission_sha,
            "composite": ev.composite,
            "dimension_scores": ev.dimension_scores,
            "evidence": ev.evidence,
            "red_flags": ev.red_flags,
            "feedback_sent": ev.feedback_draft,
            "evaluated_at": ev.created_at.isoformat(),
        })

    transcript: List[Dict[str, Any]] = [
        {
            "direction": m.direction,
            "template_id": m.template_id,
            "subject": m.subject,
            "body_preview": (m.body or "")[:300],
            "sent_by_agent": m.sent_by_agent,
            "ts": m.created_at.isoformat(),
        }
        for m in messages
    ]

    latest = evaluations[-1] if evaluations else None
    dossier = {
        "candidate_id": candidate_id,
        "name": candidate.name,
        "email": candidate.email,
        "total_rounds": len(rounds),
        "latest_composite": latest.composite if latest else None,
        "dimension_scores_latest": latest.dimension_scores if latest else {},
        "rounds": rounds,
        "transcript": transcript,
    }

    await AuditLog.append("hire_dossier_assembled", {
        "candidate_id": candidate_id,
        "composite": latest.composite if latest else None,
        "total_rounds": len(rounds),
        "transcript_messages": len(transcript),
    })

    return dossier
