import json

import anthropic

from app.config import get_anthropic_api_key
from app.schemas import AuditLog, OfferDrafterOutput
from config.models import MODELS

SYSTEM_PROMPT = """You are an offer letter drafting agent for an engineering recruiting pipeline.

You receive:
1. CANDIDATE context (name, role they applied for, composite evaluation score)
2. OFFER context (compensation, equity, benefits)
3. SENDER context (sender name, company)

Your job: Draft a professional, warm offer letter body that:
- Clearly states the role
- Summarizes compensation and equity in plain language
- Expresses genuine enthusiasm
- Invites questions

CONSTRAINTS (never violate):
- No specific start dates or deadlines ("by Monday", "start in 2 weeks", "respond within 7 days")
- No rubric language, score, or evaluation details
- No internal company nomenclature or proprietary terms
- Warm and direct — not corporate, not overly casual
- Concise — no filler paragraphs

Output ONLY valid JSON, no markdown, no preamble:
{
  "role": "the role title offered",
  "offer_details": "full multi-paragraph offer body to embed in the email template",
  "compensation_summary": "one-line internal summary of the package for audit purposes",
  "constraint_check": "PASS"
}

If you cannot draft a compliant offer, set constraint_check to "FAIL" and explain in offer_details."""

_CONFIG = MODELS["offer_drafter"]


class OfferDrafterAgent:
    @staticmethod
    async def draft(
        candidate_name: str,
        role: str,
        compensation: str,
        equity: str = "",
        benefits: str = "",
        sender_name: str = "CureForge Team",
        retries: int = 1,
    ) -> OfferDrafterOutput:
        """
        Generate a professional offer letter body using Claude Sonnet.

        Returns validated OfferDrafterOutput. Retries once on schema failure,
        then raises RuntimeError to trigger human routing.
        """
        client = anthropic.AsyncAnthropic(api_key=get_anthropic_api_key())

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
                    raise ValueError(f"Unexpected content block: {type(block)}")

                tokens_in = response.usage.input_tokens
                tokens_out = response.usage.output_tokens

                await AuditLog.append("claude_call_offer_drafter", {
                    "model": _CONFIG["model"],
                    "candidate_name": candidate_name,
                    "role": role,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost_estimate": (tokens_in * 3.0 / 1_000_000) + (tokens_out * 15.0 / 1_000_000),
                    "attempt": attempt,
                })

                parsed = json.loads(raw)
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

            except anthropic.RateLimitError:
                raise

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
