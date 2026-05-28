import json

from app.schemas import AuditLog, OfferDrafterOutput
from app.services.llm_client import call_llm
from config.models import MODELS
from app.agents._prompt_loader import load_prompt

SYSTEM_PROMPT = load_prompt("offer_drafter")

_CONFIG = MODELS["offer_drafter"]


class OfferDrafterAgent:
    @staticmethod
    async def draft(
        candidate_name: str,
        role: str,
        compensation: str,
        equity: str = "",
        benefits: str = "",
        sender_name: str = "LongevityInTime Team",
        retries: int = 1,
    ) -> OfferDrafterOutput:
        """
        Generate a professional offer letter body using Claude Sonnet.

        Returns validated OfferDrafterOutput. Retries once on schema failure,
        then raises RuntimeError to trigger human routing.
        """
        user_message = json.dumps({
            "candidate_context": {
                "candidate_name": candidate_name,
                "role": role,
            },
            "offer_context": {
                "compensation": compensation,
                "equity": equity or "not specified",
                "benefits": benefits or "standard package",
            },
            "sender_context": {
                "sender_name": sender_name,
            },
        })

        last_error = ""
        for attempt in range(retries + 1):
            try:
                resp = await call_llm(
                    system=SYSTEM_PROMPT,
                    user=user_message,
                    model=_CONFIG["model"],
                    max_tokens=_CONFIG["max_tokens"],
                    temperature=_CONFIG["temperature"],
                )

                await AuditLog.append("claude_call_offer_drafter", {
                    "model": _CONFIG["model"],
                    "candidate_name": candidate_name,
                    "role": role,
                    "tokens_in": resp.input_tokens,
                    "tokens_out": resp.output_tokens,
                    "cost_estimate": (resp.input_tokens * 3.0 / 1_000_000) + (resp.output_tokens * 15.0 / 1_000_000),
                    "attempt": attempt,
                })

                parsed = json.loads(resp.text)
                output = OfferDrafterOutput(**parsed)

                if output.constraint_check == "FAIL":
                    await AuditLog.append("offer_constraint_fail", {
                        "candidate_name": candidate_name,
                        "role": role,
                        "preview": output.offer_details[:200],
                    })

                return output

            except (json.JSONDecodeError, ValueError) as e:
                last_error = str(e)
                await AuditLog.append("offer_schema_failure", {
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
                    "agent": "offer_drafter",
                    "error": last_error,
                })

        await AuditLog.append("human_routing_triggered", {
            "reason": "offer_drafter_exhausted",
            "candidate_name": candidate_name,
        })
        raise RuntimeError(
            f"OfferDrafter failed after {retries + 1} attempts: {last_error}"
        )
