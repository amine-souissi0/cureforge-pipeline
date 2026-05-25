import base64
import json
import re
from typing import Any, Dict

import httpx

from app.config import GITHUB_API_URL, GITHUB_ORG, get_github_token
from app.schemas import AuditLog, InternalTaskSpec


class GithubService:
    """
    Async GitHub service for candidate repo provisioning.

    Creates a private repository under GITHUB_ORG, initialises it with
    a README for the candidate, and stores the internal spec on a
    separate `internal` branch that the candidate is not shown.
    """

    def __init__(self) -> None:
        self._token = get_github_token()
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def provision_repo(
        self,
        candidate_id: str,
        task_id: str,
        internal_spec: InternalTaskSpec,
    ) -> str:
        """
        Create a private repo, push a candidate README, store internal
        spec on `internal` branch. Returns the HTML repo URL.
        """
        repo_name = _make_repo_name(candidate_id, task_id)

        async with httpx.AsyncClient(base_url=GITHUB_API_URL, headers=self._headers) as client:
            repo_url = await self._create_repo(client, repo_name)
            await self._push_readme(client, repo_name)
            await self._push_internal_spec(client, repo_name, internal_spec)

        await AuditLog.append("github_repo_provisioned", {
            "candidate_id": candidate_id,
            "task_id": task_id,
            "repo_url": repo_url,
        })
        return repo_url

    async def _create_repo(self, client: httpx.AsyncClient, repo_name: str) -> str:
        # Use org endpoint if GITHUB_ORG is explicitly set, otherwise personal account
        if GITHUB_ORG and GITHUB_ORG != "cureforge-sandbox":
            endpoint = f"/orgs/{GITHUB_ORG}/repos"
        else:
            endpoint = "/user/repos"
        response = await client.post(
            endpoint,
            json={
                "name": repo_name,
                "private": True,
                "auto_init": False,
                "description": "Engineering problem — CureForge pipeline",
            },
        )
        _raise_for_status(response, "create repo")
        data: Dict[str, Any] = response.json()
        return str(data["html_url"])

    async def _push_readme(self, client: httpx.AsyncClient, repo_name: str) -> None:
        content = (
            "# Engineering Problem\n\n"
            "Please read the problem statement sent to you by email.\n\n"
            "Submit your solution by replying with a link to this repository "
            "once your work is complete.\n"
        )
        await self._create_file(
            client,
            repo_name,
            path="README.md",
            content=content,
            message="Initial commit",
            branch="main",
        )

    async def _push_internal_spec(
        self,
        client: httpx.AsyncClient,
        repo_name: str,
        spec: InternalTaskSpec,
    ) -> None:
        """Store internal spec on a separate branch — never shared with candidate."""
        spec_json = json.dumps(spec.model_dump(), indent=2)

        # Create internal branch from main
        main_sha = await self._get_branch_sha(client, repo_name, "main")
        await self._create_branch(client, repo_name, "internal", main_sha)

        await self._create_file(
            client,
            repo_name,
            path=".internal/spec.json",
            content=spec_json,
            message="Add internal spec",
            branch="internal",
        )

    async def _get_branch_sha(
        self, client: httpx.AsyncClient, repo_name: str, branch: str
    ) -> str:
        response = await client.get(
            f"/repos/{GITHUB_ORG}/{repo_name}/git/refs/heads/{branch}"
        )
        _raise_for_status(response, f"get branch SHA for {branch}")
        data: Dict[str, Any] = response.json()
        return str(data["object"]["sha"])

    async def _create_branch(
        self,
        client: httpx.AsyncClient,
        repo_name: str,
        branch: str,
        sha: str,
    ) -> None:
        response = await client.post(
            f"/repos/{GITHUB_ORG}/{repo_name}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )
        _raise_for_status(response, f"create branch {branch}")

    async def _create_file(
        self,
        client: httpx.AsyncClient,
        repo_name: str,
        path: str,
        content: str,
        message: str,
        branch: str,
    ) -> None:
        encoded = base64.b64encode(content.encode()).decode()
        response = await client.put(
            f"/repos/{GITHUB_ORG}/{repo_name}/contents/{path}",
            json={"message": message, "content": encoded, "branch": branch},
        )
        _raise_for_status(response, f"create file {path}")


def _make_repo_name(candidate_id: str, task_id: str) -> str:
    safe_id = re.sub(r"[^a-z0-9]", "-", candidate_id[:20].lower())
    safe_task = task_id[:8]
    return f"candidate-{safe_id}-{safe_task}"


def _raise_for_status(response: httpx.Response, context: str) -> None:
    if response.status_code >= 400:
        raise RuntimeError(
            f"GitHub API error ({context}): {response.status_code} — {response.text[:300]}"
        )
