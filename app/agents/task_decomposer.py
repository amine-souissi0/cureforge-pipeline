import json
from typing import Optional

import anthropic

from app.config import get_anthropic_api_key
from app.schemas import AuditLog, HeldOutTest, InternalTaskSpec, TaskDecomposerOutput
from config.blocklist import BLOCKED_TOPICS
from config.corpus import PATTERNS, CorpusPattern
from config.models import MODELS

_CONFIG = MODELS["decomposer"]

_SYSTEM_PROMPT_TEMPLATE = """You are a task decomposition agent for an engineering recruiting pipeline.

You are given:
1. CORPUS: A list of engineering patterns to select from
2. BLOCKLIST: Topics that must never appear in generated tasks
3. ROLE and LEVEL of the candidate

Your job:
1. Select ONE pattern from the corpus that exercises strong engineering fundamentals
2. Decompose it into a self-contained, sandboxed problem solvable in isolation
3. Ensure the problem is fully abstracted — no internal nomenclature, no proprietary IP
4. Verify the problem does NOT touch the blocklist (fail closed: if ambiguous, set blocklist_check=FAIL)
5. Emit two outputs:
   - candidate_brief: the problem statement the candidate receives (preamble + problem + deliverables + submission instructions)
   - internal_spec: expected behavior, held-out tests, known failure modes (NEVER sent to candidate)

CORPUS:
{corpus}

BLOCKLIST (fail closed — ambiguous counts as FAIL):
{blocklist}

CONSTRAINTS:
- candidate_brief must NEVER include: delivery timelines, rubric language, internal system names, scoring weights
- candidate_brief must be self-contained: a candidate with no context about this company must understand it fully
- internal_spec must include at least 3 held-out test cases with concrete inputs and expected outputs
- If blocklist_check is FAIL or AMBIGUOUS, set success=false

Output ONLY valid JSON, no markdown, no preamble:
{{
  "success": true,
  "corpus_pattern_selected": "pattern_id",
  "abstraction_verified": true,
  "blocklist_check": "PASS",
  "candidate_brief": "full multi-paragraph problem statement with submission instructions",
  "internal_spec": {{
    "expected_behavior": "description of a correct solution",
    "held_out_tests": [
      {{"test_id": "t1", "input": "...", "expected_output": "..."}},
      {{"test_id": "t2", "input": "...", "expected_output": "..."}},
      {{"test_id": "t3", "input": "...", "expected_output": "..."}}
    ],
    "failure_modes": ["list of common failure modes to watch for"]
  }}
}}"""


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
        preferred_pattern_id: Optional[str] = None,
        retries: int = 1,
    ) -> TaskDecomposerOutput:
        """
        Generate a task for a candidate using Claude Sonnet.

        Fail-closed: blocklist_check AMBIGUOUS or FAIL → success=False, route to human.
        """
        client = anthropic.AsyncAnthropic(api_key=get_anthropic_api_key())

        user_message = json.dumps({
            "candidate_role": candidate_role,
            "candidate_level": candidate_level,
            "preferred_pattern_id": preferred_pattern_id,
            "available_pattern_ids": list(PATTERNS.keys()),
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

                await AuditLog.append("claude_call_decomposer", {
                    "model": _CONFIG["model"],
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost_estimate": (tokens_in * 3.0 / 1_000_000) + (tokens_out * 15.0 / 1_000_000),
                    "attempt": attempt,
                })

                parsed = json.loads(raw)
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

            except anthropic.RateLimitError:
                raise

            except Exception as e:
                last_error = str(e)
                await AuditLog.append("claude_api_error", {
                    "agent": "decomposer",
                    "error": last_error,
                })

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
