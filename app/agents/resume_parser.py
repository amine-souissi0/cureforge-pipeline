"""
ResumeParserAgent: extracts a structured candidate profile from a pasted
resume/CV or self-description email. Uses call_llm so Groq/Ollama/Anthropic
all work transparently.
"""
import json
import logging
from typing import Any

from app.agents._prompt_loader import load_prompt
from app.services.llm_client import call_llm

log = logging.getLogger(__name__)

_SYSTEM = load_prompt("resume_parser")

_EMPTY_PROFILE: dict[str, Any] = {
    "skills": [],
    "years_experience": None,
    "inferred_level": "mid",
    "technologies": [],
    "preferred_roles": [],
    "location": None,
    "notice_period": None,
    "summary": "",
    "is_sufficient": False,
    "missing_fields": ["skills", "experience"],
}


class ResumeParserAgent:
    @staticmethod
    async def parse(email_body: str, candidate_role: str) -> dict[str, Any]:
        """
        Parse a pasted resume or background email.
        Returns a structured profile dict.
        Falls back to keyword extraction if the LLM call fails.
        """
        user_msg = json.dumps({
            "role_applied_for": candidate_role,
            "resume_or_background": email_body,
        })

        try:
            resp = await call_llm(
                system=_SYSTEM,
                user=user_msg,
                model="claude-3-5-haiku-20241022",
                max_tokens=700,
                temperature=0.0,
            )
            result = json.loads(resp.text)
            for k, v in _EMPTY_PROFILE.items():
                result.setdefault(k, v)
            await _audit(result)
            return result

        except Exception as exc:
            log.error("ResumeParserAgent failed: %s — falling back to keyword extraction", exc)
            return _keyword_fallback(email_body)


def _keyword_fallback(text: str) -> dict[str, Any]:
    """Best-effort keyword extraction when LLM is unavailable."""
    words = text.lower().split()
    tech = {
        "python", "java", "go", "rust", "typescript", "javascript", "sql",
        "kafka", "redis", "postgres", "postgresql", "fastapi", "django",
        "flask", "celery", "docker", "kubernetes", "aws", "gcp", "azure",
        "pytorch", "tensorflow", "spark", "airflow", "dbt", "react", "node",
    }
    found_skills = list(dict.fromkeys(w.strip(".,!?;:") for w in words if w.strip(".,!?;:") in tech))[:10]
    is_sufficient = len(found_skills) >= 2 or len(text.split()) >= 20

    # Crude notice period extraction
    notice = None
    for phrase in ["immediately", "2 weeks", "two weeks", "1 month", "one month", "2 months", "3 months"]:
        if phrase in text.lower():
            notice = phrase
            break

    # Crude location extraction — look for "based in X" or "located in X"
    location = None
    for marker in ["based in ", "located in ", "from ", "living in "]:
        idx = text.lower().find(marker)
        if idx != -1:
            rest = text[idx + len(marker):].split(".")[0].split(",")[0].strip()
            if rest:
                location = rest[:40]
            break

    return {
        "skills": found_skills,
        "years_experience": None,
        "inferred_level": "mid",
        "technologies": found_skills,
        "preferred_roles": [],
        "location": location,
        "notice_period": notice,
        "summary": text[:300].strip(),
        "is_sufficient": is_sufficient,
        "missing_fields": [] if is_sufficient else ["skills", "experience"],
    }


async def _audit(result: dict[str, Any]) -> None:
    try:
        from app.schemas import AuditLog
        await AuditLog.append("resume_parser_llm_success", {
            "is_sufficient": result.get("is_sufficient"),
            "inferred_level": result.get("inferred_level"),
            "skills_count": len(result.get("skills", [])),
        })
    except Exception:
        pass
