import json
import logging

from openai import OpenAI

from config.settings import settings
from models.database import ReplyStatus

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client

_SYSTEM_PROMPT = """\
You are an assistant that classifies investor email replies into exactly one
of four intent categories. Read the reply carefully and return a JSON object
with a single key "intent" whose value is one of:

  - "interested"      — the investor wants to learn more, schedule a call, or
                        expressed positive enthusiasm.
  - "not_interested"  — the investor declined, passed, or expressed no interest.
  - "needs_info"      — the investor asked a clarifying question or requested
                        more materials before deciding.
  - "other"           — out-of-office, unrelated, or unclassifiable message.

Return ONLY valid JSON, nothing else. Example: {"intent": "interested"}\
"""


def parse_intent(email_body: str) -> ReplyStatus:
    """
    Classify the intent of an investor's reply email using GPT-4.

    Args:
        email_body: raw plain-text or HTML body of the reply.

    Returns:
        A ReplyStatus enum value.
    """
    response = _get_client().chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": email_body},
        ],
        temperature=0.0,
        max_tokens=50,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    logger.debug("Intent parser raw response: %s", raw)

    try:
        parsed = json.loads(raw)
        intent_str = parsed.get("intent", "other").lower()
        return ReplyStatus(intent_str)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Could not parse intent from response %r: %s", raw, exc)
        return ReplyStatus.other
