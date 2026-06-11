"""
Grant Agent — Grants.gov opportunity discovery + GPT-4 narrative drafting.

What this does automatically:
  - Searches Grants.gov REST API for relevant funding opportunities
  - Queries NIH RePORTER for landscape context
  - Drafts a project narrative / specific aims (single-shot or multi-step workflow)

What still requires human action:
  - Final SF424 submission via Grants.gov Workspace or NIH ASSIST

Usage:
    from agents.grant_agent import (
        discover_grants,
        draft_narrative,
        draft_narrative_workflow,
        save_application,
        save_application_package,
        validate_project_info,
    )
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config.settings import settings
from core.http import post_json
from core.llm import chat_completion_text

logger = logging.getLogger(__name__)

GRANTS_GOV_SEARCH_URL = "https://api.grants.gov/v2/api/search2"
NIH_REPORTER_URL = "https://api.reporter.nih.gov/v2/projects/search"

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "grants"
_jinja_env: Optional[Environment] = None


def _jinja() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=select_autoescape(enabled_extensions=()),
        )
    return _jinja_env


REQUIRED_PROJECT_FIELDS = (
    "title",
    "hypothesis",
    "approach",
    "innovation",
    "team",
    "preliminary_data",
)


class GrantValidationError(ValueError):
    """Raised when project_info is missing required keys."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"project_info missing required fields: {', '.join(missing)}")


def validate_project_info(project_info: dict[str, Any]) -> None:
    """Ensure all grant narrative required fields are non-empty strings."""
    missing: list[str] = []
    for key in REQUIRED_PROJECT_FIELDS:
        val = project_info.get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(key)
    if missing:
        raise GrantValidationError(missing)


_NARRATIVE_SYSTEM_PROMPT = """\
You are an expert NIH/NSF grant writer specializing in longevity and biotech research.
Given a funding opportunity and project information, write a concise 1-page
Project Narrative / Specific Aims following NIH formatting conventions:
  • Opening paragraph — the scientific problem and significance
  • Specific Aim 1, 2, 3 — each with objective and expected outcome
  • Closing paragraph — innovation and long-term impact
Write clearly, use active voice, and stay under 750 words.\
"""

_OUTLINE_SYSTEM = """\
You are an NIH grant strategist. Given the opportunity and project facts below,
produce a tight bullet outline (max 15 bullets) for a 1-page Specific Aims style
narrative: problem, significance, 3 aims with rationale, innovation, impact.
Use Markdown bullets only, no prose paragraphs.\
"""

_CRITIQUE_SYSTEM = """\
You are a strict NIH study section reviewer. Critique the draft for: clarity,
significance, feasibility, innovation, and alignment with the stated opportunity.
List concrete issues and suggested fixes as Markdown numbered list (max 10 items).\
"""

_REFINE_SYSTEM = """\
You are an expert NIH grant writer. Revise the narrative to address every critique
while preserving factual content from the project facts. Output the full revised
narrative only (Markdown), under 750 words, same structure as a Specific Aims page.\
"""


def _render_user_prompt(opportunity: dict, project_info: dict) -> str:
    tpl = _jinja().get_template("narrative_user_prompt.j2")
    return tpl.render(opportunity=opportunity, project_info=project_info)


def discover_grants(keywords: str, limit: int = 10) -> list[dict]:
    """
    Search Grants.gov for open funding opportunities matching keywords.
    """
    payload = {
        "keyword": keywords,
        "rows": min(limit, 25),
        "oppStatuses": "posted",
        "sortBy": "openDate",
        "sortOrder": "desc",
    }

    try:
        resp = post_json(GRANTS_GOV_SEARCH_URL, payload, timeout=15.0, max_retries=2)
        data = resp.json()
    except Exception as exc:
        logger.error("Grants.gov API error: %s", exc)
        return []

    opportunities = []
    for hit in data.get("data", {}).get("hits", []):
        opportunities.append(
            {
                "opportunity_id": hit.get("id", ""),
                "title": hit.get("title", ""),
                "agency": hit.get("agencyName", ""),
                "close_date": hit.get("closeDate", ""),
                "award_ceiling": hit.get("awardCeiling", ""),
                "synopsis": hit.get("synopsis", ""),
                "url": f"https://www.grants.gov/search-results-detail/{hit.get('id', '')}",
            }
        )

    logger.info("Found %d grant opportunities for '%s'", len(opportunities), keywords)
    return opportunities


def search_nih_reporter(keywords: str, limit: int = 10) -> list[dict]:
    """
    Search NIH RePORTER for existing funded projects (landscape analysis).
    """
    payload = {
        "criteria": {"advanced_text_search": {"operator": "and", "search_field": "all", "search_text": keywords}},
        "offset": 0,
        "limit": limit,
        "sort_field": "fiscal_year",
        "sort_order": "desc",
    }

    try:
        resp = post_json(NIH_REPORTER_URL, payload, timeout=15.0, max_retries=2)
        data = resp.json()
    except Exception as exc:
        logger.error("NIH RePORTER API error: %s", exc)
        return []

    results = []
    for proj in data.get("results", []):
        pis = [p.get("full_name", "") for p in proj.get("principal_investigators", [])]
        results.append(
            {
                "project_num": proj.get("project_num", ""),
                "title": proj.get("project_title", ""),
                "fiscal_year": proj.get("fiscal_year", ""),
                "pi_names": ", ".join(pis),
                "total_cost": proj.get("total_cost", 0),
                "abstract": (proj.get("abstract_text", "") or "")[:500],
            }
        )

    logger.info("NIH RePORTER: %d results for '%s'", len(results), keywords)
    return results


def draft_narrative(
    opportunity: dict,
    project_info: dict,
    model: Optional[str] = None,
    *,
    validate: bool = True,
) -> str:
    """
    Draft a Project Narrative / Specific Aims page using GPT-4 (single pass).
    """
    if validate:
        validate_project_info(project_info)
    user_prompt = _render_user_prompt(opportunity, project_info)
    narrative = chat_completion_text(
        system_prompt=_NARRATIVE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model=model or settings.openai_model,
        temperature=0.4,
        max_tokens=1200,
    )
    logger.info("Drafted narrative for opportunity '%s'", opportunity.get("title", ""))
    return narrative


def draft_narrative_workflow(
    opportunity: dict,
    project_info: dict,
    model: Optional[str] = None,
    *,
    validate: bool = True,
    include_landscape: bool = False,
    landscape_keywords: Optional[str] = None,
) -> dict[str, str]:
    """
    Multi-step narrative: outline → draft → critique → refined narrative.

    Returns dict keys: outline, draft, critique, narrative (final).
    """
    if validate:
        validate_project_info(project_info)
    base_user = _render_user_prompt(opportunity, project_info)
    m = model or settings.openai_model

    landscape_note = ""
    if include_landscape:
        kw = landscape_keywords or project_info.get("title", "")[:120]
        landscape = search_nih_reporter(kw, limit=5)
        if landscape:
            landscape_note = "\n\n## Recent NIH landscape (for context)\n"
            landscape_note += "\n".join(
                f"- {p.get('title', '')} ({p.get('project_num', '')})" for p in landscape[:5]
            )
            base_user = base_user + landscape_note

    outline = chat_completion_text(
        system_prompt=_OUTLINE_SYSTEM,
        user_prompt=base_user,
        model=m,
        temperature=0.35,
        max_tokens=600,
    )

    draft_user = base_user + "\n\n## Approved outline\n" + outline
    draft = chat_completion_text(
        system_prompt=_NARRATIVE_SYSTEM_PROMPT,
        user_prompt=draft_user,
        model=m,
        temperature=0.45,
        max_tokens=1400,
    )

    critique = chat_completion_text(
        system_prompt=_CRITIQUE_SYSTEM,
        user_prompt=f"Opportunity:\n{base_user}\n\n## Draft\n{draft}",
        model=m,
        temperature=0.2,
        max_tokens=700,
    )

    refine_user = (
        f"{base_user}\n\n## Current draft\n{draft}\n\n## Critique\n{critique}\n\n"
        "Apply the critique and return the full improved narrative."
    )
    narrative = chat_completion_text(
        system_prompt=_REFINE_SYSTEM,
        user_prompt=refine_user,
        model=m,
        temperature=0.35,
        max_tokens=1400,
    )

    logger.info("Completed narrative workflow for '%s'", opportunity.get("title", ""))
    return {
        "outline": outline,
        "draft": draft,
        "critique": critique,
        "narrative": narrative,
    }


def save_application(
    narrative: str,
    opportunity: dict,
    output_dir: str = "output/grants",
) -> Path:
    """Save the drafted narrative to a Markdown file (legacy shape)."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    opp_id = opportunity.get("opportunity_id", "unknown").replace("/", "-")
    file_path = out / f"narrative_{opp_id}.md"

    header = (
        f"# Grant Application Draft\n\n"
        f"**Opportunity:** {opportunity.get('title', '')}\n"
        f"**Agency:** {opportunity.get('agency', '')}\n"
        f"**Close Date:** {opportunity.get('close_date', '')}\n"
        f"**URL:** {opportunity.get('url', '')}\n\n"
        f"---\n\n"
    )

    file_path.write_text(header + narrative, encoding="utf-8")
    logger.info("Saved grant narrative to %s", file_path)
    return file_path


def save_application_package(
    narrative: str,
    opportunity: dict,
    project_info: dict,
    output_dir: str = "output/grants",
    *,
    workflow_artifacts: Optional[dict[str, str]] = None,
    human_review_required: bool = True,
) -> Path:
    """
    Save narrative plus metadata.json and checklist.md for handoff to Grants.gov Workspace.

    Returns path to the package directory.
    """
    out = Path(output_dir)
    opp_id = opportunity.get("opportunity_id", "unknown").replace("/", "-")
    pkg = out / f"package_{opp_id}"
    pkg.mkdir(parents=True, exist_ok=True)

    checklist_lines = [
        "# Pre-submission checklist",
        "",
        "- [ ] PI / institution verified on SF424",
        "- [ ] Budget and budget justification attached",
        "- [ ] Biosketches current format",
        "- [ ] Facilities & other resources",
        "- [ ] Narrative pasted into agency forms and page limits checked",
        "",
        f"**Human review required:** {'yes' if human_review_required else 'no'}",
        "",
        "## Required project fields (validated)",
    ]
    for k in REQUIRED_PROJECT_FIELDS:
        checklist_lines.append(f"- [x] {k}")
    (pkg / "checklist.md").write_text("\n".join(checklist_lines), encoding="utf-8")

    meta = {
        "opportunity": opportunity,
        "project_info_keys": list(project_info.keys()),
        "human_review_required": human_review_required,
        "workflow_steps": list(workflow_artifacts.keys()) if workflow_artifacts else ["single_shot"],
    }
    if workflow_artifacts:
        meta["workflow"] = {k: (v[:2000] + "...") if len(v) > 2000 else v for k, v in workflow_artifacts.items()}
    (pkg / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    narrative_path = pkg / "narrative.md"
    header = (
        f"# Grant Application Draft\n\n"
        f"**Opportunity:** {opportunity.get('title', '')}\n"
        f"**Agency:** {opportunity.get('agency', '')}\n"
        f"**Close Date:** {opportunity.get('close_date', '')}\n"
        f"**URL:** {opportunity.get('url', '')}\n\n"
        f"---\n\n"
    )
    narrative_path.write_text(header + narrative, encoding="utf-8")

    if workflow_artifacts:
        for step, content in workflow_artifacts.items():
            if step == "narrative":
                continue
            safe = step.replace("/", "-")
            (pkg / f"artifact_{safe}.md").write_text(content, encoding="utf-8")

    logger.info("Saved grant package to %s", pkg)
    return pkg
