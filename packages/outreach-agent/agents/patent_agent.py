"""
Patent Agent — USPTO prior art search + GPT-4 provisional patent drafting.

What this does automatically:
  - Searches USPTO Full-Text database for prior art (public REST API)
  - Drafts a provisional patent application (title, background, claims, abstract)
    using GPT-4

What still requires human action:
  - Filing via USPTO Patent Center (patentcenter.uspto.gov)
    — no public filing API; requires authenticated web session
  - USPTO API key required for ODP endpoints (free, register at data.uspto.gov)
  - Have a registered patent attorney review claims before filing

Configuration (.env):
  USPTO_API_KEY=your_key_from_data.uspto.gov  (optional — some endpoints are open)
"""

import logging
from pathlib import Path
from typing import Optional

import requests
from openai import OpenAI

from config.settings import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client

# USPTO full-text search (public, no auth required)
USPTO_EFTS_URL = "https://efts.uspto.gov/LATEST/search-index"
# USPTO Open Data Portal (new ODP — requires API key)
USPTO_ODP_URL = "https://data.uspto.gov/apis/v1/patent/applications/search"

_PROVISIONAL_SYSTEM_PROMPT = """\
You are a patent attorney specializing in biotechnology and computational life sciences.
Draft a US provisional patent application for the described invention. Include:

1. TITLE OF INVENTION (clear, descriptive, under 500 chars)
2. FIELD OF THE INVENTION (1–2 sentences)
3. BACKGROUND (2–3 paragraphs: problem statement, prior art limitations)
4. SUMMARY OF THE INVENTION (2–3 paragraphs: solution overview)
5. DETAILED DESCRIPTION (3–5 paragraphs with technical detail)
6. CLAIMS (write 5–10 claims: 1 independent + dependent; use standard patent claim format)
7. ABSTRACT (150 words maximum)

Use formal patent language. Claims must be novel over the prior art references provided.\
"""


def search_prior_art(
    keywords: str,
    limit: int = 10,
    patent_type: str = "utility",
) -> list[dict]:
    """
    Search USPTO full-text database for prior art patents.

    Uses the public EFTS (ElasticSearch Full-Text Search) endpoint — no API key needed.

    Args:
        keywords:    search terms (e.g. "longevity biomarker machine learning")
        limit:       max number of results
        patent_type: "utility", "design", or "plant"

    Returns:
        List of patent dicts: patent_number, title, abstract, inventors,
        filing_date, assignee, url.
    """
    params = {
        "q": keywords,
        "f": "PatentNumber,PatentTitle,PatentAbstract,InventorName,AssigneeEntityName,ApplicationDate",
        "s": "ApplicationDate:desc",
        "rows": min(limit, 20),
        "searchType": 1,
    }

    try:
        resp = requests.get(USPTO_EFTS_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.error("USPTO EFTS search error: %s", exc)
        return []

    results = []
    for hit in data.get("hits", {}).get("hits", []):
        src = hit.get("_source", {})
        pn = src.get("PatentNumber", "")
        results.append(
            {
                "patent_number": pn,
                "title": src.get("PatentTitle", ""),
                "abstract": (src.get("PatentAbstract", "") or "")[:400],
                "inventors": src.get("InventorName", []),
                "assignee": src.get("AssigneeEntityName", ""),
                "filing_date": src.get("ApplicationDate", ""),
                "url": f"https://patents.google.com/patent/US{pn}" if pn else "",
            }
        )

    logger.info("USPTO prior art search '%s': %d results", keywords, len(results))
    return results


def search_patents_odp(
    keywords: str,
    limit: int = 10,
    api_key: Optional[str] = None,
) -> list[dict]:
    """
    Search via USPTO Open Data Portal (requires API key from data.uspto.gov).

    Falls back gracefully if no key is configured.
    """
    key = api_key or settings.uspto_api_key
    if not key:
        logger.warning("USPTO_API_KEY not set — falling back to public EFTS search.")
        return search_prior_art(keywords, limit)

    headers = {"X-API-KEY": key}
    payload = {
        "query": keywords,
        "start": 0,
        "rows": min(limit, 25),
        "fields": ["applicationNumber", "inventionTitle", "abstract", "filingDate", "assignee"],
    }

    try:
        resp = requests.post(USPTO_ODP_URL, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.error("USPTO ODP error: %s — falling back to EFTS.", exc)
        return search_prior_art(keywords, limit)

    results = []
    for item in data.get("results", []):
        results.append(
            {
                "patent_number": item.get("applicationNumber", ""),
                "title": item.get("inventionTitle", ""),
                "abstract": (item.get("abstract", "") or "")[:400],
                "filing_date": item.get("filingDate", ""),
                "assignee": item.get("assignee", ""),
                "url": "",
            }
        )
    return results


def draft_provisional(
    invention: dict,
    prior_art: Optional[list[dict]] = None,
    model: Optional[str] = None,
) -> str:
    """
    Draft a provisional patent application using GPT-4.

    Args:
        invention:  dict with keys: title, problem, solution, technical_details,
                    inventors (list), assignee (optional)
        prior_art:  list of prior art dicts from search_prior_art() (optional)
        model:      override LLM model

    Returns:
        Full provisional patent application text (Markdown-formatted).
    """
    prior_art_text = ""
    if prior_art:
        prior_art_text = "\n\nPRIOR ART REFERENCES:\n" + "\n".join(
            f"- US{p.get('patent_number', 'N/A')} — {p.get('title', '')} ({p.get('filing_date', '')})"
            for p in prior_art[:5]
        )

    user_prompt = (
        f"Invention Title: {invention.get('title', '')}\n"
        f"Problem Addressed: {invention.get('problem', '')}\n"
        f"Solution / Core Innovation: {invention.get('solution', '')}\n"
        f"Technical Details: {invention.get('technical_details', '')}\n"
        f"Inventors: {', '.join(invention.get('inventors', []))}\n"
        f"Assignee: {invention.get('assignee', 'Individual inventors')}"
        + prior_art_text
    )

    response = _get_client().chat.completions.create(
        model=model or settings.openai_model,
        messages=[
            {"role": "system", "content": _PROVISIONAL_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=2500,
    )

    draft = response.choices[0].message.content.strip()
    logger.info("Provisional patent draft generated for '%s'", invention.get("title", ""))
    return draft


def save_provisional(
    draft: str,
    invention: dict,
    output_dir: Optional[str] = None,
) -> Path:
    """
    Save a provisional patent draft with a filing instructions cover page.

    Returns:
        Path to the saved .md file.
    """
    # Gated output dir (git-ignored) — no auto-commit / auto-publish
    out = Path(output_dir or settings.patent_output_dir)
    out.mkdir(parents=True, exist_ok=True)

    safe_title = "".join(
        c if c.isalnum() or c in " _-" else "_"
        for c in invention.get("title", "provisional")
    )[:50].strip().replace(" ", "_")

    file_path = out / f"{safe_title}_provisional.md"

    instructions = f"""# USPTO Provisional Patent Application

**Status:** DRAFT — requires attorney review before filing

## Filing Instructions
1. Review and finalize all claims with a registered patent attorney
2. Go to: https://patentcenter.uspto.gov/
3. Log in with your USPTO account (register free at USPTO.gov)
4. Click "Submit New Application" → "Provisional Application"
5. Upload this document (converted to PDF) as the specification
6. Pay the micro-entity / small entity filing fee (~$320 / $640 as of 2026)
7. Save the filing receipt — you have 12 months to file the non-provisional

**Inventors:** {', '.join(invention.get('inventors', []))}
**Assignee:** {invention.get('assignee', 'Individual inventors')}

---

"""

    file_path.write_text(instructions + draft, encoding="utf-8")
    logger.info("Provisional patent saved to %s", file_path)
    return file_path
