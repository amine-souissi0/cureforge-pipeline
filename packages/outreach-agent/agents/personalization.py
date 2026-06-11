import logging
from typing import Optional

from jinja2 import Template

from config.settings import settings

logger = logging.getLogger(__name__)

# Use Groq (free) if key present, otherwise fall back to OpenAI
def _make_client():
    if settings.groq_api_key:
        from openai import OpenAI  # Groq uses OpenAI-compatible API
        return OpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
            timeout=60.0,
        ), settings.groq_model
    else:
        from openai import OpenAI
        return OpenAI(api_key=settings.openai_api_key, timeout=60.0), settings.openai_model

_client = None
_model = None


def _get_client():
    global _client, _model
    if _client is None:
        _client, _model = _make_client()
    return _client, _model


def _groq_curl(prompt: str) -> str:
    """Fallback: call Groq via requests if openai client times out."""
    import json, urllib.request
    body = json.dumps({
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 200,
        "temperature": 0.7,
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()

# Default base template — Jinja2 variables are filled by GPT-4 with context
DEFAULT_TEMPLATE = """
<p>Hi {{ name }},</p>

<p>
I'm reaching out because {{ firm }} has a strong track record investing in
{{ focus_area }}, and I believe our work at
<strong>LongevityInTime</strong> aligns closely with your thesis.
</p>

<p>
LongevityInTime is building an AI-driven platform to accelerate longevity
research — from hypothesis generation to clinical trial design — powered by
the CureForge knowledge graph. {{ personalized_hook }}
</p>

<p>
Would you be open to a 20-minute call this week or next?
</p>

<p>
Best regards,<br/>
The LongevityInTime Team
</p>
""".strip()

_SYSTEM_PROMPT = """\
You are an expert startup fundraising copywriter.
Given an investor's profile, write a single short paragraph (2–3 sentences)
called the "personalized hook" that:
  1. References something specific about their focus area or background.
  2. Explains concisely why LongevityInTime is a natural fit for them.
  3. Sounds warm, direct, and human — not salesy.
Return only the paragraph text, no extra explanation.\
"""


def personalize(investor: dict, template: Optional[str] = None) -> str:
    """
    Render a personalized HTML email body for a given investor.

    Args:
        investor: dict with keys: name, email, firm, focus_area, notes
        template: optional Jinja2 HTML template string; uses DEFAULT_TEMPLATE if None

    Returns:
        Rendered HTML string ready to be sent.
    """
    base = template or DEFAULT_TEMPLATE

    user_prompt = (
        f"Investor name: {investor.get('name', '')}\n"
        f"Firm: {investor.get('firm', '')}\n"
        f"Focus area: {investor.get('focus_area', '')}\n"
        f"Additional notes: {investor.get('notes', '')}\n"
    )

    try:
        client, model = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=200,
        )
        hook = response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("openai client failed (%s), falling back to urllib", e)
        if settings.groq_api_key:
            hook = _groq_curl(user_prompt)
        else:
            raise
    logger.debug("Generated hook for %s: %s", investor.get("email"), hook)

    rendered = Template(base).render(
        name=investor.get("name", ""),
        firm=investor.get("firm", ""),
        focus_area=investor.get("focus_area", ""),
        personalized_hook=hook,
    )
    return rendered


def default_subject(investor: dict) -> str:
    """Return a personalized email subject line for the investor."""
    return (
        f"LongevityInTime × {investor.get('firm', 'Your Fund')} — "
        "Partnering to Extend Healthy Human Lifespan"
    )
