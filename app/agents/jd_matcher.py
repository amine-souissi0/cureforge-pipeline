"""
JDMatcherAgent: scores a candidate profile against all open job definitions.
Uses call_llm so Groq/Ollama/Anthropic all work transparently.
"""
import json
import logging
from typing import Any

from app.agents._prompt_loader import load_prompt
from app.services.llm_client import call_llm
from config.jobs import JOBS

log = logging.getLogger(__name__)

_SYSTEM = load_prompt("jd_matcher")


def _jobs_payload() -> list[dict]:
    return [
        {
            "id": j.id,
            "title": j.title,
            "team": j.team,
            "levels": j.levels,
            "required_skills": j.required_skills,
            "nice_to_have": j.nice_to_have,
            "location": j.location,
            "remote_ok": j.remote_ok,
            "description": j.description,
        }
        for j in JOBS.values()
    ]


def _simple_match(profile: dict[str, Any]) -> tuple[list[dict], str | None]:
    """Keyword-based fallback matcher."""
    candidate_skills = {s.lower() for s in (profile.get("skills") or []) + (profile.get("technologies") or [])}
    candidate_level = profile.get("inferred_level", "mid")

    results = []
    for job in JOBS.values():
        req = {s.lower() for s in job.required_skills}
        nice = {s.lower() for s in job.nice_to_have}
        req_overlap = len(req & candidate_skills)
        nice_overlap = len(nice & candidate_skills)
        level_fit = 20 if candidate_level in job.levels else 5
        score = min(50, req_overlap * 12) + level_fit + min(20, nice_overlap * 4)
        gap = None if req_overlap >= max(1, len(req) // 2) else f"Missing some required skills: {', '.join(list(req - candidate_skills)[:3])}"
        results.append({
            "jd_id": job.id,
            "title": job.title,
            "score": score,
            "match_reason": f"{req_overlap}/{len(req)} required skills matched.",
            "gap": gap,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    # Filter to score >= 30, but keep at least 1
    filtered = [r for r in results if r["score"] >= 30] or results[:1]
    top = filtered[0]["jd_id"] if filtered else None
    return filtered, top


class JDMatcherAgent:
    @staticmethod
    async def match(candidate_profile: dict[str, Any]) -> dict[str, Any]:
        """
        Match candidate profile against all open jobs.
        Returns {"matches": [...sorted by score desc...], "top_jd_id": str}
        """
        user_msg = json.dumps({
            "candidate_profile": candidate_profile,
            "jobs": _jobs_payload(),
        })

        try:
            resp = await call_llm(
                system=_SYSTEM,
                user=user_msg,
                model="claude-3-5-haiku-20241022",
                max_tokens=900,
                temperature=0.0,
            )
            result = json.loads(resp.text)
            result.setdefault("matches", [])
            if not result.get("top_jd_id") and result["matches"]:
                result["top_jd_id"] = result["matches"][0]["jd_id"]
            return result

        except Exception as exc:
            log.error("JDMatcherAgent failed: %s — using simple matcher", exc)
            matches, top = _simple_match(candidate_profile)
            return {"matches": matches, "top_jd_id": top}
