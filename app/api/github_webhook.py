"""
§5.5 — GitHub webhook as alternate submission trigger.

When a candidate pushes code to their sandbox repo, GitHub fires a push event
to this endpoint. We verify the signature, map the repo URL to a candidate,
and enqueue run_submission_evaluation — same path as email-based submission.
"""
import hashlib
import hmac
import os

from fastapi import APIRouter, HTTPException, Request

from app.schemas import AuditLog

router = APIRouter(prefix="/webhook/github", tags=["github-webhook"])

_GITHUB_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")


def _verify_signature(payload: bytes, signature_header: str) -> bool:
    """Verify X-Hub-Signature-256 from GitHub."""
    if not _GITHUB_SECRET:
        return True  # secret not configured — skip verification in dev
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    mac = hmac.HMAC(_GITHUB_SECRET.encode(), payload, hashlib.sha256)
    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature_header)


@router.post("")
async def github_push(request: Request) -> dict:
    """
    Handle GitHub push webhook.
    Maps repo URL → candidate → enqueues evaluation.
    """
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_signature(body, sig):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature.")

    event = request.headers.get("X-GitHub-Event", "")
    if event != "push":
        return {"status": "ignored", "event": event}

    import json
    payload = json.loads(body)

    # Only act on pushes to the default branch
    ref = payload.get("ref", "")
    default_branch = payload.get("repository", {}).get("default_branch", "main")
    if ref != f"refs/heads/{default_branch}":
        return {"status": "ignored", "reason": "non-default-branch push"}

    repo_html_url = payload.get("repository", {}).get("html_url", "")
    if not repo_html_url:
        return {"status": "ignored", "reason": "no repo url"}

    # Map repo URL → candidate via tasks table
    from app.services.task_store import TaskStore
    task = await TaskStore.get_by_repo_url(repo_html_url)
    if task is None:
        await AuditLog.append("github_webhook_no_candidate", {"repo_url": repo_html_url})
        return {"status": "ignored", "reason": "repo not linked to any candidate"}

    await AuditLog.append("github_push_submission", {
        "candidate_id": task.candidate_id,
        "task_id": task.id,
        "repo_url": repo_html_url,
        "ref": ref,
    })

    from app.api.candidates import run_submission_evaluation
    run_submission_evaluation.delay(task.candidate_id, repo_html_url)

    return {
        "status": "evaluation_enqueued",
        "candidate_id": task.candidate_id,
        "repo_url": repo_html_url,
    }
