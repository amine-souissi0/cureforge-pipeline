"""
Journal Agent — JATS XML construction + GPT-4 cover letter drafting.

What this does automatically:
  - Builds a JATS-compliant XML file from an article dictionary
  - Drafts a personalized cover letter for the target journal using GPT-4
  - Packages both into a submission-ready directory

What still requires human action:
  - Uploading to Editorial Manager / ScholarOne / journal submission portals
    (no public submission API exists for major systems)
  - ScholarOne requires a Clarivate vendor agreement for API access

Usage:
    from agents.journal_agent import build_jats_xml, draft_cover_letter,
                                     export_submission_package
"""

import logging
from datetime import date
from pathlib import Path
from typing import Optional

try:
    from lxml import etree as _etree
    _HAS_LXML = True
except ImportError:
    _etree = None
    _HAS_LXML = False

from openai import OpenAI

from config.settings import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client

_COVER_LETTER_SYSTEM = """\
You are a senior researcher helping prepare a manuscript for journal submission.
Write a professional cover letter to the editor. The letter should:
  1. State the title and corresponding author.
  2. Briefly explain the significance and novelty (2–3 sentences).
  3. Confirm the work is original, not under review elsewhere.
  4. Suggest 3 potential reviewers (made up but plausible) if not provided.
  5. Close professionally.
Write in formal academic English. Keep under 400 words.\
"""


def build_jats_xml(article: dict) -> str:
    """
    Build a JATS 1.3 XML string from an article dictionary.

    Args:
        article: dict with keys:
            title         (str)
            abstract      (str)
            authors       (list of dict: name, affiliation, email, orcid optional)
            keywords      (list of str)
            journal       (str) — target journal name
            doi           (str, optional)
            received_date (str YYYY-MM-DD, optional)
            body_sections (list of dict: heading, text)

    Returns:
        Pretty-printed JATS XML string.
    """
    if not _HAS_LXML:
        raise ImportError("lxml package required. Install with: pip install lxml")

    etree = _etree
    today = date.today().isoformat()

    _XLINK = "http://www.w3.org/1999/xlink"
    root = etree.Element(
        "article",
        nsmap={"xlink": _XLINK},
        attrib={"article-type": "research-article", "dtd-version": "1.3"},
    )

    # ── Front matter ──────────────────────────────────────────────────────────
    front = etree.SubElement(root, "front")
    journal_meta = etree.SubElement(front, "journal-meta")
    journal_title_group = etree.SubElement(journal_meta, "journal-title-group")
    jt = etree.SubElement(journal_title_group, "journal-title")
    jt.text = article.get("journal", "")

    article_meta = etree.SubElement(front, "article-meta")

    if article.get("doi"):
        article_id = etree.SubElement(article_meta, "article-id", attrib={"pub-id-type": "doi"})
        article_id.text = article["doi"]

    # Title group
    title_group = etree.SubElement(article_meta, "title-group")
    at = etree.SubElement(title_group, "article-title")
    at.text = article.get("title", "")

    # Authors
    contrib_group = etree.SubElement(article_meta, "contrib-group")
    for idx, auth in enumerate(article.get("authors", [])):
        contrib = etree.SubElement(
            contrib_group,
            "contrib",
            attrib={"contrib-type": "author"},
        )
        if idx == 0:
            contrib.set("corresp", "yes")
        if auth.get("orcid"):
            contrib.set("id", f"auth{idx}")

        name_el = etree.SubElement(contrib, "name")
        parts = auth.get("name", "").rsplit(" ", 1)
        surname = etree.SubElement(name_el, "surname")
        surname.text = parts[-1] if len(parts) > 1 else auth.get("name", "")
        given = etree.SubElement(name_el, "given-names")
        given.text = parts[0] if len(parts) > 1 else ""

        if auth.get("email"):
            email_el = etree.SubElement(contrib, "email")
            email_el.text = auth["email"]

        if auth.get("affiliation"):
            aff = etree.SubElement(contrib_group, "aff")
            aff.text = auth["affiliation"]

    # Dates
    history = etree.SubElement(article_meta, "history")
    received = etree.SubElement(history, "date", attrib={"date-type": "received"})
    recv_date = article.get("received_date", today)
    year, month, day_ = recv_date.split("-") if "-" in recv_date else (today[:4], today[5:7], today[8:])
    etree.SubElement(received, "year").text = year
    etree.SubElement(received, "month").text = month
    etree.SubElement(received, "day").text = day_

    # Keywords
    if article.get("keywords"):
        kwd_group = etree.SubElement(article_meta, "kwd-group", attrib={"kwd-group-type": "author"})
        for kw in article["keywords"]:
            kwd = etree.SubElement(kwd_group, "kwd")
            kwd.text = kw

    # Abstract
    abstract_el = etree.SubElement(article_meta, "abstract")
    abstract_p = etree.SubElement(abstract_el, "p")
    abstract_p.text = article.get("abstract", "")

    # ── Body ─────────────────────────────────────────────────────────────────
    body = etree.SubElement(root, "body")
    for section in article.get("body_sections", []):
        sec = etree.SubElement(body, "sec")
        title_s = etree.SubElement(sec, "title")
        title_s.text = section.get("heading", "")
        p = etree.SubElement(sec, "p")
        p.text = section.get("text", "")

    # ── Back matter ───────────────────────────────────────────────────────────
    back = etree.SubElement(root, "back")
    ack = etree.SubElement(back, "ack")
    ack_p = etree.SubElement(ack, "p")
    ack_p.text = article.get("acknowledgements", "")

    xml_bytes = etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    )
    return xml_bytes.decode("utf-8")


def draft_cover_letter(
    article: dict,
    journal: str,
    editor_name: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    Draft a cover letter for journal submission using GPT-4.

    Args:
        article:      article dict (uses title, abstract, authors)
        journal:      target journal name
        editor_name:  optional editor name for salutation
        model:        override LLM model

    Returns:
        Cover letter as plain text.
    """
    salutation = f"Dear Dr. {editor_name}" if editor_name else "Dear Editor"
    first_author = article.get("authors", [{}])[0].get("name", "Corresponding Author")

    user_prompt = (
        f"Journal: {journal}\n"
        f"Salutation: {salutation}\n"
        f"Manuscript Title: {article.get('title', '')}\n"
        f"Corresponding Author: {first_author}\n"
        f"Abstract Summary: {article.get('abstract', '')[:600]}\n"
        f"Keywords: {', '.join(article.get('keywords', []))}\n"
    )

    response = _get_client().chat.completions.create(
        model=model or settings.openai_model,
        messages=[
            {"role": "system", "content": _COVER_LETTER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=600,
    )

    letter = response.choices[0].message.content.strip()
    logger.info("Drafted cover letter for '%s' → %s", article.get("title", ""), journal)
    return letter


def export_submission_package(
    article: dict,
    journal: str,
    output_dir: str = "output/journal",
    editor_name: Optional[str] = None,
) -> Path:
    """
    Build a complete submission package: JATS XML + cover letter + checklist.

    Returns:
        Path to the output directory.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # JATS XML
    jats_xml = build_jats_xml({**article, "journal": journal})
    (out / "manuscript.jats.xml").write_text(jats_xml, encoding="utf-8")

    # Cover letter
    cover = draft_cover_letter(article, journal, editor_name)
    (out / "cover_letter.txt").write_text(cover, encoding="utf-8")

    # Manual submission checklist
    checklist = f"""# Journal Submission Checklist — {journal}

Automated: JATS XML generated, cover letter drafted.
Manual: Upload to the journal's submission portal.

## Files in this package
- manuscript.jats.xml   — structured manuscript (JATS 1.3)
- cover_letter.txt      — personalized cover letter

## Submission Portals
- Editorial Manager portals: https://www.editorialmanager.com/<journal-code>/
- ScholarOne portals:        https://mc.manuscriptcentral.com/<journal-code>/
- PLoS ONE:                  https://plos.org/publish/submit/
- eLife:                     https://submit.elifesciences.org/

## Checklist
- [ ] Manuscript PDF prepared and formatted per journal guidelines
- [ ] All author affiliations and ORCIDs verified
- [ ] Cover letter reviewed and updated
- [ ] Conflicts of interest declared
- [ ] Data availability statement added
- [ ] Supplementary files labeled and uploaded separately
- [ ] Journal's word/figure count limits checked
- [ ] Submission fee (if applicable) arranged
"""
    (out / "checklist.md").write_text(checklist, encoding="utf-8")

    logger.info("Journal submission package saved to %s", out)
    return out
