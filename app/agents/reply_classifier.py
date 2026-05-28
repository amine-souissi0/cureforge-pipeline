import json
from app.schemas import ReplyClassifierOutput, AuditLog
from app.services.llm_client import call_llm
from config.models import MODELS
from app.agents._prompt_loader import load_prompt

SYSTEM_PROMPT = load_prompt("classifier")

_CONFIG = MODELS["classifier"]


class ReplyClassifierAgent:
    @staticmethod
    async def classify_email(
        email_body: str,
        candidate_context: str,
        candidate_state: str = "",
        retries: int = 1,
    ) -> ReplyClassifierOutput:
        user_message = json.dumps({
            "email_body": email_body,
            "candidate_context": candidate_context,
            "candidate_state": candidate_state,
        })

        last_error: str = ""
        for attempt in range(retries + 1):
            try:
                resp = await call_llm(
                    system=SYSTEM_PROMPT,
                    user=user_message,
                    model=_CONFIG["model"],
                    max_tokens=_CONFIG["max_tokens"],
                    temperature=_CONFIG["temperature"],
                )

                await AuditLog.append("claude_call_classifier", {
                    "model": _CONFIG["model"],
                    "tokens_in": resp.input_tokens,
                    "tokens_out": resp.output_tokens,
                    "cost_estimate": (resp.input_tokens * 0.25 / 1_000_000) + (resp.output_tokens * 1.25 / 1_000_000),
                    "attempt": attempt,
                })

                parsed = json.loads(resp.text)
                output = ReplyClassifierOutput(**parsed)
                return output

            except (json.JSONDecodeError, ValueError) as e:
                last_error = str(e)
                await AuditLog.append("schema_validation_failure", {
                    "attempt": attempt,
                    "error": last_error,
                })
                if attempt < retries:
                    user_message = (
                        user_message
                        + f"\n\nPrevious output was invalid: {last_error}. Return ONLY the JSON object."
                    )

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
            # Candidate signalled a submission but omitted the URL — ask for it explicitly
            return "request_submission_url"
        return f"submission_intake:{submission_url}"

    if output.intent == "DECLINE":
        return "fsm_withdrawn"

    if output.intent == "BACKGROUND_SUBMITTED":
        return "background_intake"

    if output.intent == "JD_INTERESTED":
        jd_title = (output.extracted or {}).get("jd_title") or ""
        return f"jd_confirmed:{jd_title}"

    if output.intent == "JD_NOT_INTERESTED":
        return "jd_declined"

    # INTERESTED, QUESTION, SCHEDULING
    return f"template_responder:{output.intent}"
