from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.fsm import CandidateState, FSMEngine
from app.models import TaskModel
from app.schemas import AuditLog
from app.services.task_store import TaskStore

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    candidate_id: str
    candidate_role: str = "software engineer"
    candidate_level: str = "senior"
    preferred_pattern_id: Optional[str] = None


class TaskResponse(BaseModel):
    task_id: str
    candidate_id: str
    corpus_ref: Optional[str]
    candidate_brief: str
    repo_url: Optional[str]
    # internal_spec deliberately excluded — never exposed via API


class ProvisionRepoRequest(BaseModel):
    candidate_id: str


class SendBriefRequest(BaseModel):
    candidate_id: str
    to_email: str
    sender_name: str = "CureForge Team"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/generate")
async def generate_task(payload: GenerateRequest) -> Dict[str, Any]:
    """
    Run the Task Decomposer agent for a candidate.

    On success: stores the task and returns task_id + candidate_brief preview.
    On blocklist rejection or LLM failure: routes to human review.
    """
    from app.agents.task_decomposer import TaskDecomposerAgent, validate_no_blocklist_terms

    output = await TaskDecomposerAgent.decompose(
        candidate_role=payload.candidate_role,
        candidate_level=payload.candidate_level,
        preferred_pattern_id=payload.preferred_pattern_id,
    )

    if not output.success or output.blocklist_check != "PASS":
        await AuditLog.append("task_generation_rejected", {
            "candidate_id": payload.candidate_id,
            "blocklist_check": output.blocklist_check,
            "reason": "decomposer_rejected",
        })
        raise HTTPException(
            status_code=422,
            detail={
                "error": "task_rejected",
                "blocklist_check": output.blocklist_check,
                "action": "routed_to_human_review",
            },
        )

    # Post-generation safety scan
    violations = validate_no_blocklist_terms(output.candidate_brief)
    if violations:
        await AuditLog.append("task_post_scan_violation", {
            "candidate_id": payload.candidate_id,
            "violations": violations,
        })
        raise HTTPException(
            status_code=422,
            detail={"error": "post_scan_violation", "terms": violations},
        )

    task = TaskModel(
        candidate_id=payload.candidate_id,
        candidate_brief=output.candidate_brief,
        internal_spec=output.internal_spec.model_dump() if output.internal_spec else {},
        corpus_ref=output.corpus_pattern_selected,
    )
    task_id = await TaskStore.add(task)

    return {
        "task_id": task_id,
        "candidate_id": payload.candidate_id,
        "corpus_ref": output.corpus_pattern_selected,
        "status": "generated",
        "brief_preview": output.candidate_brief[:200],
    }


@router.get("/{task_id}")
async def get_task(task_id: str) -> TaskResponse:
    """Retrieve a task. internal_spec is never returned."""
    task = await TaskStore.get_by_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found.")
    return TaskResponse(
        task_id=task.id,
        candidate_id=task.candidate_id,
        corpus_ref=task.corpus_ref,
        candidate_brief=task.candidate_brief,
        repo_url=task.repo_url,
    )


@router.post("/{task_id}/provision-repo")
async def provision_repo(task_id: str, payload: ProvisionRepoRequest) -> Dict[str, Any]:
    """
    Provision a private GitHub sandbox repo for the candidate.
    Stores internal spec on the `internal` branch (hidden from candidate).
    """
    from app.services.github_service import GithubService
    from app.schemas import InternalTaskSpec

    task = await TaskStore.get_by_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found.")

    if task.repo_url:
        return {"task_id": task_id, "repo_url": task.repo_url, "status": "already_provisioned"}

    internal_spec = InternalTaskSpec(**task.internal_spec) if task.internal_spec else InternalTaskSpec(
        expected_behavior="See task spec.",
        held_out_tests=[],
        failure_modes=[],
    )

    try:
        svc = GithubService()
        repo_url = await svc.provision_repo(
            candidate_id=payload.candidate_id,
            task_id=task_id,
            internal_spec=internal_spec,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    await TaskStore.update_repo_url(task_id, repo_url)
    return {"task_id": task_id, "repo_url": repo_url, "status": "provisioned"}


@router.post("/{task_id}/send-brief")
async def send_brief(task_id: str, payload: SendBriefRequest) -> Dict[str, Any]:
    """
    Send the candidate_brief via the Template Responder and trigger FSM transitions:
    ENGAGED → TASK_ASSIGNED → AWAITING_SUBMISSION (when repo is also provisioned).
    """
    from app.agents.template_responder import TemplateResponderAgent
    from app.services.approval_queue import ApprovalQueue, DraftEmail
    from app.services.send_policy import SendMode, get_send_mode

    task = await TaskStore.get_by_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found.")

    result = await TemplateResponderAgent.render(
        template_id="task-assignment-cover",
        candidate_context={
            "candidate_name": payload.candidate_id,
            "sender_name": payload.sender_name,
        },
        extra_context={"task_brief": task.candidate_brief},
    )

    if result.constraint_check == "FAIL":
        raise HTTPException(status_code=422, detail="Template constraint violation.")

    mode = get_send_mode(payload.candidate_id, "task-assignment-cover")

    if mode == SendMode.AUTO:
        from app.services.gmail_service import GmailService
        svc = GmailService()
        gmail_id = await svc.send_email(
            to=payload.to_email,
            subject=result.subject,
            body=result.body,
        )
        brief_sent = True
        response: Dict[str, Any] = {"status": "sent", "gmail_id": gmail_id}
    else:
        draft = DraftEmail(
            candidate_id=payload.candidate_id,
            template_id="task-assignment-cover",
            subject=result.subject,
            body=result.body,
            to_email=payload.to_email,
        )
        draft_id = await ApprovalQueue.add(draft)
        brief_sent = False
        response = {"status": "draft", "draft_id": draft_id}

    # FSM: ENGAGED → TASK_ASSIGNED (requires intent + task_id)
    fsm = FSMEngine()
    await fsm.transition(
        candidate_id=payload.candidate_id,
        target_state=CandidateState.TASK_ASSIGNED,
        context={"intent": "INTERESTED", "task_id": task_id},
        actor="task_api",
    )

    # FSM: TASK_ASSIGNED → AWAITING_SUBMISSION (requires brief sent + repo provisioned)
    if brief_sent and task.repo_url:
        await fsm.transition(
            candidate_id=payload.candidate_id,
            target_state=CandidateState.AWAITING_SUBMISSION,
            context={"task_brief_sent": True, "repo_url": task.repo_url},
            actor="task_api",
        )

    response["task_id"] = task_id
    return response
