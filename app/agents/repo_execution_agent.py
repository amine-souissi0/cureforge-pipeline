"""
Repo Execution Agent — analyses a candidate's GitHub submission to determine
how to run it against held-out tests.

Uses Claude Haiku to read the file tree + README and identify:
  - Which file contains the implementation (entry_file)
  - The exact function name the candidate used

This feeds the sandbox runner so it calls the right function, even if the
candidate used a slightly different name or split code across files.
"""

import json
import logging
from typing import Any, Dict, List

from app.schemas import AuditLog, RepoExecutionPlan
from app.services.llm_client import call_llm
from config.models import MODELS
from app.agents._prompt_loader import load_prompt

log = logging.getLogger(__name__)

_CONFIG = MODELS["repo_analyzer"]
_SYSTEM_PROMPT = load_prompt("repo_analyzer")


class RepoExecutionAgent:
    @staticmethod
    async def analyze(
        repo_url: str,
        file_tree: List[Dict[str, Any]],
        readme_content: str,
        expected_function_name: str,
        expected_behavior: str,
    ) -> RepoExecutionPlan:
        """
        Inspect a candidate's repo and return an execution plan.

        Falls back to expected_function_name with confidence=0.5 if the
        LLM cannot determine the entry point.
        """
        # Filter tree to Python files only (exclude obvious non-impl files)
        py_files = [
            item["path"]
            for item in file_tree
            if item.get("type") == "blob"
            and item["path"].endswith(".py")
            and not _is_support_file(item["path"])
        ]

        user_message = json.dumps({
            "file_tree": py_files,
            "readme": readme_content[:2000],
            "expected_function_name": expected_function_name,
            "expected_behavior": expected_behavior,
        })

        try:
            resp = await call_llm(
                system=_SYSTEM_PROMPT,
                user=user_message,
                model=_CONFIG["model"],
                max_tokens=_CONFIG["max_tokens"],
                temperature=_CONFIG["temperature"],
            )

            await AuditLog.append("claude_call_repo_analyzer", {
                "model": _CONFIG["model"],
                "tokens_in": resp.input_tokens,
                "tokens_out": resp.output_tokens,
                "repo_url": repo_url,
            })

            parsed = json.loads(resp.text)
            plan = RepoExecutionPlan(**parsed)

            await AuditLog.append("repo_execution_plan", {
                "repo_url": repo_url,
                "entry_file": plan.entry_file,
                "function_name": plan.function_name,
                "confidence": plan.confidence,
            })
            return plan

        except Exception as e:
            log.warning("RepoExecutionAgent failed (%s), falling back to expected function name", e)
            await AuditLog.append("repo_execution_plan_fallback", {
                "repo_url": repo_url,
                "error": str(e),
                "fallback_function": expected_function_name,
            })
            # Fallback: trust the internal spec's function name
            return RepoExecutionPlan(
                entry_file="solution.py",
                function_name=expected_function_name or "solution",
                confidence=0.5,
                reasoning="fallback — LLM analysis failed",
            )


def _is_support_file(path: str) -> bool:
    """True for files that are clearly not the main implementation."""
    name = path.split("/")[-1].lower()
    return any(name.startswith(p) for p in ("test_", "conftest", "setup", "__init__")) or \
           name in ("requirements.txt", "readme.md", "dockerfile", "makefile")
