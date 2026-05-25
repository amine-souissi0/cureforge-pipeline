import json
from typing import Any, Dict, List

import anthropic

from app.config import get_anthropic_api_key
from app.schemas import AuditLog, EvaluationAgentOutput
from app.services.sandbox_runner import SandboxResult
from config.models import MODELS
from config.rubric import DIMENSIONS, compute_composite
from app.agents._prompt_loader import load_prompt

_CONFIG = MODELS["evaluator"]

_SYSTEM_PROMPT = load_prompt("evaluator")


def _build_system_prompt() -> str:
    rubric_text = "\n".join(
        f"- {d.id} (weight={d.weight}): {d.description}"
        for d in DIMENSIONS.values()
    )
    return _SYSTEM_PROMPT.format(rubric=rubric_text)


class EvaluationAgent:
    @staticmethod
    async def evaluate(
        source_code: str,
        sandbox_result: SandboxResult,
        internal_spec: Dict[str, Any],
        candidate_round: int = 1,
        retries: int = 1,
    ) -> EvaluationAgentOutput:
        """
        Score a candidate submission using Claude Opus.

        The composite is always recomputed from dimension_scores to prevent
        the model from inventing a number inconsistent with its own scores.
        """
        client = anthropic.AsyncAnthropic(api_key=get_anthropic_api_key())

        sandbox_summary = _format_sandbox_result(sandbox_result)
        user_message = json.dumps({
            "source_code_preview": source_code[:3000],
            "sandbox_results": sandbox_summary,
            "internal_spec": internal_spec,
            "candidate_round": candidate_round,
        })

        system_prompt = _build_system_prompt()
        last_error = ""

        for attempt in range(retries + 1):
            try:
                response = await client.messages.create(
                    model=_CONFIG["model"],
                    max_tokens=_CONFIG["max_tokens"],
                    temperature=_CONFIG["temperature"],
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )

                block = response.content[0]
                raw = getattr(block, "text", None)
                if not isinstance(raw, str):
                    raise ValueError(f"Unexpected content block: {type(block)}")

                tokens_in = response.usage.input_tokens
                tokens_out = response.usage.output_tokens

                await AuditLog.append("claude_call_evaluator", {
                    "model": _CONFIG["model"],
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost_estimate": (tokens_in * 15.0 / 1_000_000) + (tokens_out * 75.0 / 1_000_000),
                    "attempt": attempt,
                    "round": candidate_round,
                })

                parsed = json.loads(raw)
                output = EvaluationAgentOutput(**parsed)

                # Always recompute composite from dimension scores — do not trust model's value
                recomputed = compute_composite(output.dimension_scores)
                if abs(recomputed - output.composite) > 0.5:
                    await AuditLog.append("composite_recomputed", {
                        "model_composite": output.composite,
                        "recomputed": recomputed,
                    })
                output = output.model_copy(update={"composite": recomputed})

                _validate_no_rubric_leak(output.candidate_feedback_draft)
                return output

            except (json.JSONDecodeError, ValueError) as e:
                last_error = str(e)
                await AuditLog.append("evaluation_schema_failure", {
                    "attempt": attempt,
                    "error": last_error,
                })
                if attempt < retries:
                    user_message = (
                        user_message
                        + f"\n\nPrevious output was invalid: {last_error}. Return ONLY the JSON."
                    )

            except anthropic.RateLimitError:
                raise

            except Exception as e:
                last_error = str(e)
                await AuditLog.append("claude_api_error", {
                    "agent": "evaluator",
                    "error": last_error,
                })

        await AuditLog.append("human_routing_triggered", {
            "reason": "evaluation_agent_exhausted",
            "last_error": last_error,
        })
        raise RuntimeError(f"EvaluationAgent failed after {retries + 1} attempts: {last_error}")


def _format_sandbox_result(result: SandboxResult) -> Dict[str, Any]:
    return {
        "ran": result.ran,
        "pass_rate": result.pass_rate,
        "passed": result.passed_tests,
        "failed": result.failed_tests,
        "total": result.total_tests,
        "sandbox_error": result.sandbox_error,
        "test_details": [
            {
                "test_id": r.test_id,
                "passed": r.passed,
                "stdout": r.stdout[:500],
                "stderr": r.stderr[:500],
                "execution_ms": r.execution_ms,
                "error": r.error,
            }
            for r in result.test_results
        ],
    }


_RUBRIC_LEAK_TERMS = [
    "correctness_verification",
    "invariant_failclosed",
    "structure_determinism",
    "testing_instrumentation",
    "communication_iteration",
    "weight",
    "dimension",
    "rubric",
    "composite score",
]


def _validate_no_rubric_leak(feedback: str) -> None:
    """Raise if candidate feedback contains internal rubric terminology."""
    lower = feedback.lower()
    for term in _RUBRIC_LEAK_TERMS:
        if term in lower:
            raise ValueError(f"Rubric leak detected in candidate feedback: {term!r}")


def get_dimension_ids() -> List[str]:
    return list(DIMENSIONS.keys())
