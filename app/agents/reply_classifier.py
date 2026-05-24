import json
import anthropic
from app.config import get_anthropic_api_key
from app.schemas import ReplyClassifierOutput, AuditLog
from config.models import MODELS

SYSTEM_PROMPT = """You are an email intent classifier for an engineering recruiting pipeline.

Classify the candidate's email into ONE of these intents:
- INTERESTED: Candidate expresses interest in the role
- QUESTION: Candidate asks clarifying questions
- SCHEDULING: Candidate proposes a meeting or call
- TASK_SUBMISSION: Candidate submits a GitHub repo link for the task
- DECLINE: Candidate declines the opportunity
- OTHER: None of the above; ambiguous

Output ONLY valid JSON, no markdown, no preamble:
{
  "intent": "INTERESTED | QUESTION | SCHEDULING | TASK_SUBMISSION | DECLINE | OTHER",
  "confidence": 0.0,
  "extracted": {
    "questions": ["list of explicit questions if QUESTION intent"],
    "submission_url": "full GitHub URL if TASK_SUBMISSION intent; null otherwise"
  },
  "summary": "one-line internal summary for logging"
}

Be precise. If confidence < 0.75, set intent to OTHER.

CONSTRAINT: Output ONLY the JSON object. No explanation, no preamble, no markdown fences."""

_CONFIG = MODELS["classifier"]


class ReplyClassifierAgent:
    @staticmethod
    async def classify_email(
        email_body: str,
        candidate_context: str,
        retries: int = 1,
    ) -> ReplyClassifierOutput:
        client = anthropic.AsyncAnthropic(api_key=get_anthropic_api_key())

        user_message = json.dumps({
            "email_body": email_body,
            "candidate_context": candidate_context,
        })

        last_error: str = ""
        for attempt in range(retries + 1):
            try:
                response = await client.messages.create(
                    model=_CONFIG["model"],
                    max_tokens=_CONFIG["max_tokens"],
                    temperature=_CONFIG["temperature"],
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_message}],
                )

                block = response.content[0]
                raw = getattr(block, "text", None)
                if not isinstance(raw, str):
                    raise ValueError(f"Unexpected content block type: {type(block)}")

                tokens_in = response.usage.input_tokens
                tokens_out = response.usage.output_tokens

                await AuditLog.append("claude_call_classifier", {
                    "model": _CONFIG["model"],
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost_estimate": (tokens_in * 0.25 / 1_000_000) + (tokens_out * 1.25 / 1_000_000),
                    "attempt": attempt,
                })

                parsed = json.loads(raw)
                output = ReplyClassifierOutput(**parsed)
                return output

            except (json.JSONDecodeError, ValueError) as e:
                last_error = str(e)
                await AuditLog.append("schema_validation_failure", {
                    "attempt": attempt,
                    "error": last_error,
                })
                if attempt < retries:
                    # Retry with stricter prompt reminder
                    user_message = (
                        user_message
                        + f"\n\nPrevious output was invalid: {last_error}. Return ONLY the JSON object."
                    )

            except anthropic.RateLimitError:
                raise

            except Exception as e:
                last_error = str(e)
                await AuditLog.append("claude_api_error", {"error": last_error, "attempt": attempt})

        await AuditLog.append("human_routing_triggered", {
            "reason": "schema_failure_exhausted",
            "last_error": last_error,
        })
        return ReplyClassifierOutput(
            intent="OTHER",
            confidence=0.0,
            reasoning="Failed to parse Claude output after retries",
        )


def route_classified_email(output: ReplyClassifierOutput, candidate_id: str) -> str:
    """
    Route a classified email to the appropriate downstream handler.
    Returns the routing decision string for audit logging.
    """
    if not output.is_high_confidence():
        return "human_review"

    if output.intent == "TASK_SUBMISSION":
        submission_url = (output.extracted or {}).get("submission_url")
        if not submission_url:
            return "human_review_no_url"
        return f"submission_intake:{submission_url}"

    if output.intent == "DECLINE":
        return "fsm_withdrawn"

    # INTERESTED, QUESTION, SCHEDULING
    return f"template_responder:{output.intent}"
