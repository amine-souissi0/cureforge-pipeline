import json
from typing import Dict

from app.schemas import AuditLog, TemplateResponderOutput
from app.services.llm_client import call_llm
from app.templates import TemplateRegistry
from config.models import MODELS
from config.templates import TEMPLATES
from app.agents._prompt_loader import load_prompt

SYSTEM_PROMPT = load_prompt("templater")

_CONFIG = MODELS["templater"]


class TemplateResponderAgent:
    @staticmethod
    async def render(
        template_id: str,
        candidate_context: Dict[str, str],
        extra_context: Dict[str, str] | None = None,
        retries: int = 1,
    ) -> TemplateResponderOutput:
        """
        Use Claude Haiku to populate a template and return a validated output.

        Falls back to direct rendering (no LLM) for the acknowledgment template,
        which is simple enough to render deterministically.
        """
        if template_id not in TEMPLATES:
            raise KeyError(f"Unknown template: {template_id!r}")

        # These templates have all fields known at call time — skip LLM, render directly
        _DIRECT_RENDER = {"acknowledgment", "task-assignment-cover", "warm-hold", "initial-outreach"}
        if template_id in _DIRECT_RENDER:
            return _render_direct(template_id, {**(candidate_context or {}), **(extra_context or {})})

        tmpl = TEMPLATES[template_id]
        user_message = json.dumps({
            "template_id": template_id,
            "subject_template": tmpl.subject_template,
            "body_template": tmpl.body_template,
            "required_fields": tmpl.required_fields,
            "candidate_context": candidate_context,
            "extra_context": extra_context or {},
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

                await AuditLog.append("claude_call_templater", {
                    "model": _CONFIG["model"],
                    "template_id": template_id,
                    "tokens_in": resp.input_tokens,
                    "tokens_out": resp.output_tokens,
                    "cost_estimate": (resp.input_tokens * 0.25 / 1_000_000) + (resp.output_tokens * 1.25 / 1_000_000),
                    "attempt": attempt,
                })

                parsed = json.loads(resp.text)
                output = TemplateResponderOutput(**parsed)

                if output.constraint_check == "FAIL":
                    await AuditLog.append("template_constraint_fail", {
                        "template_id": template_id,
                        "body_preview": output.body[:200],
                    })

                return output

            except (json.JSONDecodeError, ValueError) as e:
                last_error = str(e)
                await AuditLog.append("template_schema_failure", {
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
                await AuditLog.append("claude_api_error", {"agent": "templater", "error": last_error})

        await AuditLog.append("human_routing_triggered", {
            "reason": "template_responder_exhausted",
            "template_id": template_id,
        })
        raise RuntimeError(
            f"TemplateResponder failed after {retries + 1} attempts: {last_error}"
        )


def _render_direct(template_id: str, fields: Dict[str, str]) -> TemplateResponderOutput:
    """Render simple templates deterministically without LLM."""
    subject, body = TemplateRegistry.render(template_id, fields)
    return TemplateResponderOutput(
        template_id=template_id,
        subject=subject,
        body=body,
        fields_used=list(fields.keys()),
        constraint_check="PASS",
    )
