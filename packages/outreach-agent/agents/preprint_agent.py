"""
Preprint Agent — arXiv SWORD v2 submission + bioRxiv/medRxiv preparation.

What this does automatically:
  - Searches arXiv for related papers (via arxiv SDK)
  - Submits manuscripts to arXiv via SWORD v2 protocol (fully automated)
  - Generates a bioRxiv submission checklist + metadata file (human submits)

What still requires human action:
  - bioRxiv / medRxiv: no programmatic API — human must upload at biorxiv.org
  - arXiv: account must have SWORD access enabled and credentials configured

Configuration (.env):
  ARXIV_USERNAME=your_arxiv_username
  ARXIV_PASSWORD=your_arxiv_password
"""

import logging
import tarfile
import tempfile
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

try:
    import arxiv
    _HAS_ARXIV = True
except ImportError:
    _HAS_ARXIV = False

import requests
from requests.auth import HTTPBasicAuth

from config.settings import settings

logger = logging.getLogger(__name__)

ARXIV_SWORD_URL = "https://arxiv.org/sword-app/"

# Atom namespace for SWORD v2 entry
_ATOM_NS = "http://www.w3.org/2005/Atom"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_ARXIV_NS = "http://arxiv.org/schemas/atom"


def search_arxiv(
    query: str,
    max_results: int = 5,
    category: Optional[str] = None,
) -> list[dict]:
    """
    Search arXiv for papers matching a query.

    Args:
        query:       search string (supports arXiv query syntax)
        max_results: number of results to return
        category:    optional arXiv category filter (e.g. "q-bio.GN", "cs.AI")

    Returns:
        List of paper dicts: id, title, authors, published, summary, pdf_url, categories.
    """
    if not _HAS_ARXIV:
        raise ImportError("arxiv package required. Install with: pip install arxiv")

    search_query = query
    if category:
        search_query = f"cat:{category} AND ({query})"

    search = arxiv.Search(
        query=search_query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance,
    )

    results = []
    client = arxiv.Client()
    for paper in client.results(search):
        results.append(
            {
                "id": paper.entry_id,
                "title": paper.title,
                "authors": [a.name for a in paper.authors],
                "published": paper.published.isoformat() if paper.published else "",
                "summary": paper.summary[:500],
                "pdf_url": paper.pdf_url,
                "categories": paper.categories,
            }
        )

    logger.info("arXiv search '%s': %d results", query, len(results))
    return results


def _build_atom_entry(metadata: dict) -> bytes:
    """
    Build a SWORD v2 Atom entry XML for an arXiv submission.

    metadata keys: title, summary, authors (list), category, comments (optional)
    """
    ET.register_namespace("", _ATOM_NS)
    ET.register_namespace("dc", _DC_NS)
    ET.register_namespace("arxiv", _ARXIV_NS)

    entry = ET.Element(f"{{{_ATOM_NS}}}entry")

    title_el = ET.SubElement(entry, f"{{{_ATOM_NS}}}title")
    title_el.text = metadata["title"]

    summary_el = ET.SubElement(entry, f"{{{_ATOM_NS}}}summary")
    summary_el.text = metadata["summary"]

    for author_name in metadata.get("authors", []):
        author_el = ET.SubElement(entry, f"{{{_ATOM_NS}}}author")
        name_el = ET.SubElement(author_el, f"{{{_ATOM_NS}}}name")
        name_el.text = author_name

    cat_el = ET.SubElement(entry, f"{{{_ARXIV_NS}}}primary_category")
    cat_el.set("term", metadata.get("category", "q-bio.GN"))

    if metadata.get("comments"):
        comments_el = ET.SubElement(entry, f"{{{_ARXIV_NS}}}comments")
        comments_el.text = metadata["comments"]

    return ET.tostring(entry, encoding="unicode", xml_declaration=False).encode("utf-8")


def submit_to_arxiv(
    metadata: dict,
    source_tar_path: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> str:
    """
    Submit a manuscript to arXiv via SWORD v2 protocol.

    Args:
        metadata:        dict with keys: title, summary, authors, category, comments
        source_tar_path: path to .tar.gz of LaTeX source files
        username:        arXiv username (defaults to ARXIV_USERNAME in .env)
        password:        arXiv password (defaults to ARXIV_PASSWORD in .env)

    Returns:
        arXiv submission ID string on success.

    Raises:
        ValueError:  if credentials are missing
        RuntimeError: if SWORD deposit fails
    """
    user = username or settings.arxiv_username
    pwd = password or settings.arxiv_password

    if not user or not pwd:
        raise ValueError(
            "arXiv credentials required. Set ARXIV_USERNAME and ARXIV_PASSWORD in .env"
        )

    atom_entry = _build_atom_entry(metadata)
    source_path = Path(source_tar_path)

    if not source_path.exists():
        raise FileNotFoundError(f"Source archive not found: {source_tar_path}")

    with open(source_path, "rb") as f:
        source_bytes = f.read()

    # SWORD v2 multipart deposit
    boundary = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/atom+xml; charset=UTF-8\r\n"
        f"Content-Disposition: attachment; name=atom\r\n\r\n"
    ).encode("utf-8")
    body += atom_entry
    body += (
        f"\r\n--{boundary}\r\n"
        f"Content-Type: application/x-gzip\r\n"
        f"Content-Disposition: attachment; name=payload; filename={source_path.name}\r\n\r\n"
    ).encode("utf-8")
    body += source_bytes
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")

    headers = {
        "Content-Type": f"multipart/related; boundary={boundary}",
        "X-Packaging": "http://arxiv.org/help/submit",
        "X-No-Op": "false",
        "X-Verbose": "false",
    }

    resp = requests.post(
        ARXIV_SWORD_URL,
        data=body,
        headers=headers,
        auth=HTTPBasicAuth(user, pwd),
        timeout=60,
    )

    if resp.status_code not in (200, 201, 202):
        raise RuntimeError(
            f"arXiv SWORD deposit failed [{resp.status_code}]: {resp.text[:500]}"
        )

    # Extract submission ID from response Location header or body
    submission_id = resp.headers.get("Location", "")
    if not submission_id:
        submission_id = resp.text[:200]

    logger.info("arXiv SWORD deposit accepted. Submission: %s", submission_id)
    return submission_id


def prepare_biorxiv_submission(
    article: dict,
    output_dir: str = "output/preprints",
) -> Path:
    """
    Generate a bioRxiv/medRxiv submission metadata file and checklist.

    bioRxiv has no programmatic API — this creates a ready-to-paste metadata
    file and step-by-step checklist for manual upload at biorxiv.org.

    Args:
        article: dict with keys: title, abstract, authors, category,
                 keywords, pdf_path, cover_letter (optional)
        output_dir: where to save the prep files

    Returns:
        Path to the output directory.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    authors_formatted = "\n".join(
        f"  - {a}" for a in article.get("authors", [])
    )

    metadata_content = f"""# bioRxiv / medRxiv Submission Metadata

**Title:** {article.get('title', '')}

**Category:** {article.get('category', '')}

**Keywords:** {', '.join(article.get('keywords', []))}

## Authors
{authors_formatted}

## Abstract
{article.get('abstract', '')}

## Cover Letter
{article.get('cover_letter', '(add cover letter here)')}
"""

    checklist_content = """# bioRxiv Submission Checklist

bioRxiv submission is web-form only. Use the metadata file alongside this
checklist at: https://www.biorxiv.org/submit-a-manuscript

## Before Submitting
- [ ] PDF is finalized and under 10MB
- [ ] All authors have been notified and approved submission
- [ ] No identifying information in PDF (for double-blind journals, remove later)
- [ ] Supplementary files are labeled and referenced in the main text
- [ ] Category selected matches the primary field (see metadata file)
- [ ] Abstract is ≤ 150 words (check word count)
- [ ] Keywords entered (5–10 recommended)

## At biorxiv.org
1. Go to https://www.biorxiv.org/submit-a-manuscript
2. Create account / log in
3. Click "New Submission"
4. Select category from metadata file
5. Paste title and abstract from metadata file
6. Add authors in order listed
7. Upload PDF
8. Add keywords from metadata file
9. Paste cover letter if required
10. Submit — you will receive a confirmation email

## After Submission
- [ ] Note your bioRxiv DOI (issued within 24h on weekdays)
- [ ] Share DOI with collaborators and on social media
- [ ] Update your records with preprint DOI
"""

    (out / "biorxiv_metadata.md").write_text(metadata_content, encoding="utf-8")
    (out / "biorxiv_checklist.md").write_text(checklist_content, encoding="utf-8")

    logger.info("bioRxiv submission prep saved to %s", out)
    return out
