"""
BackgroundExtractorAgent: parses a candidate's background email and infers
their seniority level and skills so the task can be calibrated correctly.
"""
import json
import logging
from typing import Any

from anthropic import Anthropic

from app.config import get_anthropic_api_key

log = logging.getLogger(__name__)

_SYSTEM = """You are a technical recruiter assistant. A candidate has replied describing their background.

Extract the following from their message and output ONLY valid JSON, no markdown, no preamble:
{
  "inferred_level": "junior | mid | senior | staff | principal",
  "years_experience": <integer or null>,
  "key_skills": ["comma-separated technical skills, max 8"],
  "summary": "2-3 sentence internal summary of candidate background for task calibration"
}

Level inference rules:
- junior: <2 years, student, bootcamp, first job
- mid: 2-4 years, works independently, has shipped features
- senior: 5-8 years, leads work, owns systems, mentors others
- staff: 8+ years, cross-team impact, architecture decisions
- principal: 10+ years, org-wide technical direction

If the candidate is vague, default to "mid".
Output ONLY the JSON object."""


class BackgroundExtractorAgent:
    @staticmethod
    async def extract(email_body: str, candidate_role: str) -> dict[str, Any]:
        """
        Parse a background email and return extracted profile.
        Falls back to a safe default if parsing fails.
        """
        default = {
            "inferred_level": "mid",
            "years_experience": None,
            "key_skills": [],
            "summary": email_body[:300].strip(),
        }

        try:
            api_key = get_anthropic_api_key()
        except Exception:
            api_key = ""

        if not api_key:
            log.warning("BackgroundExtractorAgent: no API key, using default")
            return default

        try:
            client = Anthropic(api_key=api_key)
            user_msg = json.dumps({
                "role_applied_for": candidate_role,
                "candidate_message": email_body,
            })
            response = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=400,
                temperature=0.0,
                system=_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = response.content[0].text.strip()
            result = json.loads(raw)
            # Ensure required keys present
            result.setdefault("inferred_level", "mid")
            result.setdefault("key_skills", [])
            result.setdefault("summary", default["summary"])
            return result
        except Exception as exc:
            log.error("BackgroundExtractorAgent failed: %s", exc)
            return default
