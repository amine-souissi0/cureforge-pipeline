"""
Reply classifier — uses Groq to decide if a reply needs human review.

Rules:
  - Template/auto-replies (OOO, bounce, "we'll be in touch", NDR) → reply_status = "pending", no forward
  - Genuine replies showing real engagement → forward to olegteterinjr@gmail.com + mark as "interested" or "needs_info"
  - Clear rejections ("not accepting", "not a fit") → reply_status = "not_interested", no forward

The HITL forwarding email is sent via Resend from outreach@contact.longevityintime.org
to olegteterinjr@gmail.com so the boss sees the conversation in his inbox.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Literal

from config.settings import settings

logger = logging.getLogger(__name__)

REVIEW_EMAIL = "olegteterinjr@gmail.com"

_SYSTEM_PROMPT = """\
You are an AI assistant helping a longevity biotech startup (LongevityInTime / CureForge)
decide how to handle investor email replies.

Classify the reply into ONE of these categories:

1. "template" — automated or generic:
   - Out-of-office / vacation responders
   - Bounce / NDR / undeliverable messages
   - Generic "thanks, we'll be in touch if interested" with NO specific mention of the company
   - Newsletter unsubscribe confirmations

2. "rejection" — clear no:
   - "Not investing in longevity / not a fit"
   - "Not accepting unsolicited pitches"
   - Politely but clearly declining

3. "interested" — positive engagement:
   - Asking for more info / deck / meeting
   - Expressing genuine curiosity about the company
   - Requesting a call or intro

4. "needs_info" — requires response but not clearly interested:
   - Asking clarifying questions before deciding
   - Asking to be added to a waitlist or future round
   - Mild positive signals with a pending question

Respond in JSON only. Format:
{"category": "<template|rejection|interested|needs_info>", "reason": "<one sentence>"}
"""


def classify_reply(
    reply_text: str,
    sender: str = "",
    subject: str = "",
) -> dict:
    """
    Classify a reply email.

    Returns:
        {"category": str, "reason": str}
    """
    user_msg = (
        f"From: {sender}\n"
        f"Subject: {subject}\n\n"
        f"Reply text:\n{reply_text[:2000]}"
    )

    body = json.dumps({
        "model": settings.groq_model or "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system",  "content": _SYSTEM_PROMPT},
            {"role": "user",    "content": user_msg},
        ],
        "max_tokens":  120,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }).encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type":  "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            result = json.loads(r.read())
            content = result["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as e:
        logger.error("classify_reply failed: %s", e)
        return {"category": "needs_info", "reason": "Classification error — manual review needed"}


def should_forward(category: Literal["template", "rejection", "interested", "needs_info"]) -> bool:
    """Only forward genuine engagement to the boss."""
    return category in ("interested", "needs_info")


def forward_to_boss(
    original_sender: str,
    original_subject: str,
    reply_text: str,
    firm_name: str,
    category: str,
    reason: str,
) -> bool:
    """
    Forward a genuine reply to olegteterinjr@gmail.com via Resend.
    Returns True on success.
    """
    import resend
    resend.api_key = settings.resend_api_key

    tag = "🔥 Interested" if category == "interested" else "❓ Needs Info"
    subject = f"[HITL] {tag} — {firm_name}: {original_subject}"

    html = f"""
<p><strong>AI Classification:</strong> {tag}<br/>
<strong>Reason:</strong> {reason}</p>

<p><strong>From:</strong> {original_sender}<br/>
<strong>Firm:</strong> {firm_name}<br/>
<strong>Original Subject:</strong> {original_subject}</p>

<hr/>
<blockquote style="border-left:3px solid #888; padding-left:12px; color:#555;">
{reply_text.replace(chr(10), '<br/>')}
</blockquote>

<hr/>
<p style="color:#888; font-size:12px;">
This email was forwarded by the CureForge AI outreach agent.<br/>
Only replies requiring your personal review are forwarded here.
</p>
"""

    try:
        params: resend.Emails.SendParams = {
            "from":    settings.from_email,
            "to":      [REVIEW_EMAIL],
            "subject": subject,
            "html":    html,
            "reply_to": original_sender,  # so boss can reply directly
        }
        resp = resend.Emails.send(params)
        logger.info("Forwarded reply from %s to boss — id=%s", firm_name, resp.get("id"))
        return True
    except Exception as e:
        logger.error("Failed to forward reply from %s: %s", firm_name, e)
        return False
