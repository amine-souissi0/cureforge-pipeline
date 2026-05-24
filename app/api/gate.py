from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.fsm import CandidateState, FSMEngine
from app.schemas import AuditLog
from app.services.evaluation_store import EvaluationStore
from app.services.task_store import TaskStore

router = APIRouter(prefix="/gate", tags=["gate"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class DecideRequest(BaseModel):
    evaluation_id: str
    to_email: str
    sender_name: str = "CureForge Team"
    mode: str = "recommend"   # "recommend" | "autonomous"


class OverrideRequest(BaseModel):
    target_state: str         # e.g. "HIRE_RECOMMENDED", "WARM_HOLD", "WITHDRAWN"
    reviewer: str = "founder"
    reason: str = ""


class ResubmitRequest(BaseModel):
    task_id: str
    submission_sha: str
    source_code: str
    to_email: str
    sender_name: str = "CureForge Team"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/{candidate_id}/decide")
async def decide_gate(candidate_id: str, payload: DecideRequest) -> Dict[str, Any]:
    """
    Run the full feedback loop for a candidate after evaluation:
    send feedback email, run decision engine, execute FSM transition.
    """
    from app.services.feedback_controller import run_feedback_loop

    evaluation = await EvaluationStore.get_by_id(payload.evaluation_id)
    if evaluation is None:
        raise HTTPException(
            status_code=404,
            detail=f"Evaluation {payload.evaluation_id!r} not found.",
        )
    if evaluation.candidate_id != candidate_id:
        raise HTTPException(
            status_code=400,
            detail="Evaluation does not belong to this candidate.",
        )

    result = await run_feedback_loop(
        candidate_id=candidate_id,
        evaluation_id=payload.evaluation_id,
        to_email=payload.to_email,
        sender_name=payload.sender_name,
        mode=payload.mode,
    )

    return {
        "candidate_id": candidate_id,
        "composite": result.composite,
        "round": result.round_number,
        "next_state": result.decision.next_state.value,
        "reasoning": result.decision.reasoning,
        "requires_founder_approval": result.decision.requires_founder_approval,
        "feedback_draft_id": result.feedback_draft_id,
        "fsm_transitioned": result.fsm_transitioned,
    }


@router.post("/{candidate_id}/override")
async def override_gate(candidate_id: str, payload: OverrideRequest) -> Dict[str, Any]:
    """
    Founder override — force-write any valid FSM state, bypassing transition predicates.
    Intended for manual pipeline corrections. Every override is audit-logged.
    """
    try:
        target = CandidateState(payload.target_state)
    except ValueError:
        valid = [s.value for s in CandidateState]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid state {payload.target_state!r}. Valid states: {valid}",
        )

    from app.services.candidate_store import CandidateStore
    candidate = await CandidateStore.get_by_id(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id!r} not found.")

    fsm = FSMEngine()
    previous_state = await fsm.force_set_state(
        candidate_id=candidate_id,
        target_state=target,
        actor=payload.reviewer,
        reason=payload.reason,
    )

    await AuditLog.append("founder_override", {
        "candidate_id": candidate_id,
        "previous_state": previous_state.value,
        "target_state": payload.target_state,
        "reviewer": payload.reviewer,
        "reason": payload.reason,
    })

    return {
        "candidate_id": candidate_id,
        "previous_state": previous_state.value,
        "current_state": payload.target_state,
        "reviewer": payload.reviewer,
    }


@router.post("/{candidate_id}/resubmit")
async def resubmit(candidate_id: str, payload: ResubmitRequest) -> Dict[str, Any]:
    """
    Candidate submits a revised solution.
    Pins new SHA, re-runs sandbox + evaluation agent.
    FSM: AWAITING_RESUBMISSION → UNDER_EVALUATION → FEEDBACK_SENT
    """
    from app.agents.evaluation_agent import EvaluationAgent
    from app.models import EvaluationModel
    from app.services.sandbox_runner import SandboxRunner

    task = await TaskStore.get_by_id(payload.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {payload.task_id!r} not found.")

    fsm = FSMEngine()

    # AWAITING_RESUBMISSION → UNDER_EVALUATION
    await fsm.transition(
        candidate_id=candidate_id,
        target_state=CandidateState.UNDER_EVALUATION,
        context={"resubmission_sha": payload.submission_sha},
        actor="gate_api",
    )

    await AuditLog.append("resubmission_pinned", {
        "candidate_id": candidate_id,
        "task_id": payload.task_id,
        "sha": payload.submission_sha,
    })

    round_number = await EvaluationStore.get_round_count(candidate_id) + 1
    held_out_tests = task.internal_spec.get("held_out_tests", [])

    sandbox_result = SandboxRunner.run(
        source_code=payload.source_code,
        held_out_tests=held_out_tests,
    )

    await AuditLog.append("resubmit_sandbox_complete", {
        "candidate_id": candidate_id,
        "pass_rate": sandbox_result.pass_rate,
    })

    try:
        agent_output = await EvaluationAgent.evaluate(
            source_code=payload.source_code,
            sandbox_result=sandbox_result,
            internal_spec=task.internal_spec,
            candidate_round=round_number,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    from app.services.evaluation_store import EvaluationStore as ES
    evaluation = EvaluationModel(
        candidate_id=candidate_id,
        round=round_number,
        submission_sha=payload.submission_sha,
        dimension_scores=agent_output.dimension_scores,
        composite=agent_output.composite,
        evidence={"evidence_summary": agent_output.evidence_summary},
        red_flags=agent_output.red_flags,
        feedback_draft=agent_output.candidate_feedback_draft,
    )
    evaluation_id = await ES.add(evaluation)

    # UNDER_EVALUATION → FEEDBACK_SENT
    await fsm.transition(
        candidate_id=candidate_id,
        target_state=CandidateState.FEEDBACK_SENT,
        context={"evaluation_record_id": evaluation_id},
        actor="gate_api",
    )

    return {
        "candidate_id": candidate_id,
        "evaluation_id": evaluation_id,
        "round": round_number,
        "composite": agent_output.composite,
        "sandbox_pass_rate": sandbox_result.pass_rate,
        "status": "resubmission_evaluated",
    }


@router.get("/{candidate_id}/status")
async def gate_status(candidate_id: str) -> Dict[str, Any]:
    """Current gate status — evaluation history and latest decision context."""
    evaluations = await EvaluationStore.list_by_candidate(candidate_id)
    latest = await EvaluationStore.get_latest_by_candidate(candidate_id)

    if latest is None:
        return {
            "candidate_id": candidate_id,
            "rounds_completed": 0,
            "latest_composite": None,
            "evaluations": [],
        }

    from app.services.decision_engine import decide
    decision = decide(
        composite=latest.composite,
        rounds_completed=len(evaluations),
    )

    return {
        "candidate_id": candidate_id,
        "rounds_completed": len(evaluations),
        "latest_composite": latest.composite,
        "latest_round": latest.round,
        "projected_next_state": decision.next_state.value,
        "projected_reasoning": decision.reasoning,
        "evaluations": [
            {"round": e.round, "composite": e.composite, "sha": e.submission_sha}
            for e in evaluations
        ],
    }
