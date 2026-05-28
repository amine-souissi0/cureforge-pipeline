import json
from typing import Optional

from app.schemas import AuditLog, TaskDecomposerOutput
from app.services.llm_client import call_llm
from config.blocklist import BLOCKED_TOPICS
from config.corpus import PATTERNS, CorpusPattern
from config.models import MODELS
from app.agents._prompt_loader import load_prompt

_CONFIG = MODELS["decomposer"]

_SYSTEM_PROMPT_TEMPLATE = load_prompt("decomposer")


def _build_system_prompt() -> str:
    corpus_text = "\n".join(
        f"- id={p.id} | domain={p.domain} | {p.description}"
        for p in PATTERNS.values()
    )
    blocklist_text = "\n".join(f"- {topic}" for topic in BLOCKED_TOPICS)
    return _SYSTEM_PROMPT_TEMPLATE.format(corpus=corpus_text, blocklist=blocklist_text)


class TaskDecomposerAgent:
    @staticmethod
    async def decompose(
        candidate_role: str,
        candidate_level: str,
        background_notes: str = "",
        preferred_pattern_id: Optional[str] = None,
        retries: int = 1,
    ) -> TaskDecomposerOutput:
        """
        Generate a task for a candidate using Claude Sonnet.

        Fail-closed: blocklist_check AMBIGUOUS or FAIL → success=False, route to human.
        """
        user_message = json.dumps({
            "candidate_role": candidate_role,
            "candidate_level": candidate_level,
            "candidate_background": background_notes or None,
            "preferred_pattern_id": preferred_pattern_id,
            "available_pattern_ids": list(PATTERNS.keys()),
        })

        system_prompt = _build_system_prompt()
        last_error = ""

        for attempt in range(retries + 1):
            try:
                resp = await call_llm(
                    system=system_prompt,
                    user=user_message,
                    model=_CONFIG["model"],
                    max_tokens=_CONFIG["max_tokens"],
                    temperature=_CONFIG["temperature"],
                )

                await AuditLog.append("claude_call_decomposer", {
                    "model": _CONFIG["model"],
                    "tokens_in": resp.input_tokens,
                    "tokens_out": resp.output_tokens,
                    "cost_estimate": (resp.input_tokens * 3.0 / 1_000_000) + (resp.output_tokens * 15.0 / 1_000_000),
                    "attempt": attempt,
                })

                parsed = json.loads(resp.text)
                output = TaskDecomposerOutput(**parsed)

                # Fail-closed blocklist enforcement
                if output.blocklist_check in ("FAIL", "AMBIGUOUS") or not output.success:
                    await AuditLog.append("task_blocklist_rejected", {
                        "blocklist_check": output.blocklist_check,
                        "pattern": output.corpus_pattern_selected,
                    })
                    output = TaskDecomposerOutput(
                        success=False,
                        corpus_pattern_selected=output.corpus_pattern_selected,
                        abstraction_verified=output.abstraction_verified,
                        blocklist_check=output.blocklist_check,
                        candidate_brief="",
                        internal_spec=None,
                    )

                return output

            except (json.JSONDecodeError, ValueError) as e:
                last_error = str(e)
                await AuditLog.append("task_schema_failure", {
                    "attempt": attempt,
                    "error": last_error,
                })
                if attempt < retries:
                    user_message = (
                        user_message
                        + f"\n\nPrevious output was invalid: {last_error}. Return ONLY the JSON."
                    )

            except Exception as e:
                last_error = str(e)
                await AuditLog.append("claude_api_error", {
                    "agent": "decomposer",
                    "error": last_error,
                })
                # Don't retry on hard API errors (rate limit, auth) — raise immediately
                raise

        await AuditLog.append("human_routing_triggered", {
            "reason": "task_decomposer_exhausted",
            "last_error": last_error,
        })
        return TaskDecomposerOutput(
            success=False,
            corpus_pattern_selected="unknown",
            abstraction_verified=False,
            blocklist_check="FAIL",
            candidate_brief="",
            internal_spec=None,
        )


def validate_no_blocklist_terms(text: str) -> list[str]:
    """
    Post-generation safety check: scan candidate_brief for blocklist terms.
    Returns list of found violations (empty = clean).
    """
    text_lower = text.lower()
    return [term for term in BLOCKED_TOPICS if term.lower() in text_lower]


def get_pattern(pattern_id: str) -> Optional[CorpusPattern]:
    return PATTERNS.get(pattern_id)
