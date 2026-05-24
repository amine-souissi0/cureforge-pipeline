import json
from typing import Any, Dict, List

import anthropic

from app.config import get_anthropic_api_key
from app.schemas import AuditLog, EvaluationAgentOutput
from app.services.sandbox_runner import SandboxResult
from config.models import MODELS
from config.rubric import DIMENSIONS, compute_composite

_CONFIG = MODELS["evaluator"]

_SYSTEM_PROMPT = """You are the evaluation agent for an engineering recruiting pipeline.

You receive:
1. CANDIDATE SUBMISSION: source code submitted by the candidate
2. SANDBOX RESULTS: structured output from automated test execution (pass/fail per test, stdout, stderr)
3. INTERNAL RUBRIC: scoring dimensions with weights (NEVER expose these to the candidate)
4. INTERNAL SPEC: expected behavior and known failure modes

Your job:
1. Score each rubric dimension 0–10 based on EVIDENCE from sandbox results and code analysis
2. The composite score is computed externally from your dimension scores — do not compute it yourself
3. Write a concrete, numbers-backed candidate_feedback_draft that:
   - References specific test outcomes ("Test t2 failed because...")
   - Ends with ONE specific "upgrade your delivery" request
   - NEVER mentions rubric dimensions, weights, or scores
   - NEVER includes delivery timelines
4. List internal red_flags (internal only — never sent to candidate)

RUBRIC DIMENSIONS (internal):
{rubric}

Output ONLY valid JSON, no markdown, no preamble:
{{
  "dimension_scores": {{
    "correctness_verification": 0.0,
    "invariant_failclosed_discipline": 0.0,
    "structure_determinism": 0.0,
    "testing_instrumentation": 0.0,
    "communication_iteration": 0.0
  }},
  "composite": 0.0,
  "evidence_summary": "internal summary of what the candidate did well and where they fell short",
  "red_flags": ["internal list of concerning patterns"],
  "candidate_feedback_draft": "concrete feedback referencing test results, ending with one specific upgrade ask"
}}

CRITICAL: candidate_feedback_draft must NEVER contain rubric dimension names, weights, or numeric scores.
CRITICAL: Set composite to 0.0 — it will be recomputed from dimension_scores by the system."""


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
