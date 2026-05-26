from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.fsm import CandidateState, FSMEngine
from app.models import EvaluationModel
from app.schemas import AuditLog
from app.services.evaluation_store import EvaluationStore
from app.services.task_store import TaskStore

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


async def _queue_feedback_draft(
    candidate_id: str,
    feedback_text: str,
    upgrade_ask: str,
    round_number: int,
) -> None:
    """Queue a feedback-delivery draft for founder approval after evaluation."""
    from app.services.approval_queue import ApprovalQueue, DraftEmail
    from app.services.candidate_store import CandidateStore
    from app.templates import TemplateRegistry

    candidate = await CandidateStore.get_by_id(candidate_id)
    if candidate is None:
        return

    subject, body = TemplateRegistry.render("feedback-delivery", {
        "candidate_name": candidate.name,
        "feedback": feedback_text,
        "upgrade_ask": upgrade_ask or "Please address the gaps above and resubmit.",
        "sender_name": "CureForge Team",
    })

    draft = DraftEmail(
        candidate_id=candidate_id,
        template_id="feedback-delivery",
        subject=subject,
        body=body,
        to_email=candidate.email,
    )
    draft_id = await ApprovalQueue.add(draft)
    await AuditLog.append("feedback_draft_queued", {
        "candidate_id": candidate_id,
        "draft_id": draft_id,
        "round": round_number,
    })


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SubmitRequest(BaseModel):
    candidate_id: str
    submission_sha: str          # git SHA of pinned submission commit
    source_code: str             # raw source code for sandbox execution
    task_id: str


class EvaluationResponse(BaseModel):
    evaluation_id: str
    candidate_id: str
    round: int
    composite: float
    candidate_feedback: str
    submission_sha: str
    # dimension_scores and red_flags deliberately excluded


class EvaluationSummary(BaseModel):
    evaluation_id: str
    round: int
    composite: float
    submission_sha: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_response(evaluation: EvaluationModel) -> EvaluationResponse:
    """Build API response — never exposes dimension_scores or red_flags."""
    return EvaluationResponse(
        evaluation_id=evaluation.id,
        candidate_id=evaluation.candidate_id,
        round=evaluation.round,
        composite=evaluation.composite,
        candidate_feedback=evaluation.feedback_draft,
        submission_sha=evaluation.submission_sha,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/submit")
async def submit_evaluation(payload: SubmitRequest) -> Dict[str, Any]:
    """
    Pin submission SHA, run sandbox, score with Evaluation Agent.

    FSM transitions:
      AWAITING_SUBMISSION → UNDER_EVALUATION (submission_sha_pinned)
      UNDER_EVALUATION    → FEEDBACK_SENT    (evaluation_complete)
    """
    from app.agents.evaluation_agent import EvaluationAgent
    from app.services.sandbox_runner import SandboxRunner

    task = await TaskStore.get_by_id(payload.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {payload.task_id!r} not found.")

    fsm = FSMEngine()

    # Pin SHA → UNDER_EVALUATION
    await fsm.transition(
        candidate_id=payload.candidate_id,
        target_state=CandidateState.UNDER_EVALUATION,
        context={"submission_sha": payload.submission_sha},
        actor="evaluation_api",
    )

    await AuditLog.append("submission_pinned", {
        "candidate_id": payload.candidate_id,
        "task_id": payload.task_id,
        "submission_sha": payload.submission_sha,
    })

    # Determine round number
    round_number = await EvaluationStore.get_round_count(payload.candidate_id) + 1

    # Run sandbox against held-out tests
    held_out_tests: List[Dict[str, Any]] = task.internal_spec.get("held_out_tests", [])
    sandbox_result = SandboxRunner.run(
        source_code=payload.source_code,
        held_out_tests=held_out_tests,
    )

    await AuditLog.append("sandbox_complete", {
        "candidate_id": payload.candidate_id,
        "pass_rate": sandbox_result.pass_rate,
        "passed": sandbox_result.passed_tests,
        "total": sandbox_result.total_tests,
    })

    # Score with Evaluation Agent
    try:
        agent_output = await EvaluationAgent.evaluate(
            source_code=payload.source_code,
            sandbox_result=sandbox_result,
            internal_spec=task.internal_spec,
            candidate_round=round_number,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Persist evaluation record
    evaluation = EvaluationModel(
        candidate_id=payload.candidate_id,
        round=round_number,
        submission_sha=payload.submission_sha,
        dimension_scores=agent_output.dimension_scores,
        composite=agent_output.composite,
        evidence={"evidence_summary": agent_output.evidence_summary},
        red_flags=agent_output.red_flags,
        feedback_draft=agent_output.candidate_feedback_draft,
    )
    evaluation_id = await EvaluationStore.add(evaluation)

    # FSM: UNDER_EVALUATION → FEEDBACK_SENT
    await fsm.transition(
        candidate_id=payload.candidate_id,
        target_state=CandidateState.FEEDBACK_SENT,
        context={"evaluation_record_id": evaluation_id},
        actor="evaluation_api",
    )

    # Queue feedback draft for founder approval
    await _queue_feedback_draft(
        candidate_id=payload.candidate_id,
        feedback_text=agent_output.candidate_feedback_draft,
        upgrade_ask="",
        round_number=round_number,
    )

    return {
        "evaluation_id": evaluation_id,
        "candidate_id": payload.candidate_id,
        "round": round_number,
        "composite": agent_output.composite,
        "sandbox_pass_rate": sandbox_result.pass_rate,
        "status": "evaluation_complete",
    }


@router.get("/{evaluation_id}")
async def get_evaluation(evaluation_id: str) -> EvaluationResponse:
    """Get evaluation result — red_flags and dimension_scores never returned."""
    evaluation = await EvaluationStore.get_by_id(evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail=f"Evaluation {evaluation_id!r} not found.")
    return _safe_response(evaluation)


@router.get("/candidate/{candidate_id}")
async def list_candidate_evaluations(candidate_id: str) -> Dict[str, Any]:
    """List all evaluation rounds for a candidate."""
    evaluations = await EvaluationStore.list_by_candidate(candidate_id)
    summaries = [
        EvaluationSummary(
            evaluation_id=e.id,
            round=e.round,
            composite=e.composite,
            submission_sha=e.submission_sha,
        ).model_dump()
        for e in evaluations
    ]
    return {
        "candidate_id": candidate_id,
        "total_rounds": len(summaries),
        "evaluations": summaries,
    }


@router.get("/candidate/{candidate_id}/feedback")
async def get_candidate_feedback(candidate_id: str) -> Dict[str, Any]:
    """Return only the candidate-facing feedback from the latest evaluation."""
    evaluation = await EvaluationStore.get_latest_by_candidate(candidate_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="No evaluations found for this candidate.")
    return {
        "candidate_id": candidate_id,
        "round": evaluation.round,
        "feedback": evaluation.feedback_draft,
    }
