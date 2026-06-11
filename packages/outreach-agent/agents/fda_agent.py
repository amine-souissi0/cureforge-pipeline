"""
FDA Agent — eCTD package builder + ESG NextGen programmatic upload.

What this does automatically:
  - Builds an eCTD-compliant directory structure and index.xml backbone (lxml)
  - Authenticates with FDA ESG NextGen via OAuth 2.0
  - Obtains presigned S3 credentials and uploads the package
  - Polls submission status via ESG NextGen REST API

What still requires human action:
  - eCTD validation with certified software (Lorenz docuBridge, Extedo, Veeva Vault)
    — no open-source tool passes full FDA validation criteria
  - FDA ESG NextGen account registration (https://esgng.fda.gov/)
  - Obtaining client_id / client_secret from FDA Unified Submission Portal
  - Clinical/regulatory review of all Module content before submission

Configuration (.env):
  FDA_CLIENT_ID=your_client_id
  FDA_CLIENT_SECRET=your_client_secret

Reference:
  FDA ESG NextGen API Guide v1.2 (March 2026):
  https://www.fda.gov/media/191613/download
"""

import hashlib
import logging
import os
import zipfile
from datetime import date
from pathlib import Path
from typing import Optional

try:
    import boto3 as _boto3
    _HAS_BOTO3 = True
except ImportError:
    _boto3 = None
    _HAS_BOTO3 = False

try:
    from lxml import etree as _etree
    _HAS_LXML = True
except ImportError:
    _etree = None
    _HAS_LXML = False

import requests

from config.settings import settings

logger = logging.getLogger(__name__)

# ESG NextGen base URL
ESG_BASE_URL = "https://esgng.fda.gov"
ESG_TOKEN_URL = f"{ESG_BASE_URL}/as/token.oauth2"
ESG_CREDENTIALS_URL = f"{ESG_BASE_URL}/api/esgng/v1/credentials/api"
ESG_STATUS_URL = f"{ESG_BASE_URL}/api/esgng/v1/submissions/{{submission_id}}/status"

# eCTD Module structure (abbreviated — Module 1 + stubs for 2-5)
_ECTD_MODULES = {
    "1": "Regional Administrative Information",
    "2": "Common Technical Document Summaries",
    "3": "Quality",
    "4": "Nonclinical Study Reports",
    "5": "Clinical Study Reports",
}


def build_ectd_package(
    study_info: dict,
    output_dir: str = "output/fda",
    *,
    manifest: Optional[dict] = None,
    prose: Optional[str] = None,
) -> Path:
    """
    Build an eCTD-compliant directory structure with index.xml backbone.

    Args:
        study_info: dict with keys:
            application_type  ("IND" or "NDA")
            application_number (str, e.g. "IND-123456" or "" for new)
            sponsor_name      (str)
            drug_name         (str)
            sequence_number   (str, e.g. "0000" for initial)
            study_title       (str)
            indication        (str)
            documents         (list of dict: module, section, title, file_path)
        output_dir: root directory for the eCTD package

    Returns:
        Path to the eCTD package directory.
    """
    if not _HAS_LXML:
        raise ImportError("lxml package required. Install with: pip install lxml")

    if manifest is not None:
        from ind_validation.gate import validate_ind

        result = validate_ind(manifest, prose or "")
        if result["validation_status"] != "passed":
            hid = result.get("hypothesis_id") or manifest.get("hypothesis_id") or "(unknown)"
            logger.error(
                "IND validation gate blocked packaging hypothesis_id=%s failures=%s",
                hid,
                result.get("failures", []),
            )
            raise ValueError(
                "IND validation gate failed — packaging blocked. "
                + "; ".join(result.get("failures", [])[:5])
            )

    today = date.today().isoformat().replace("-", "")
    seq = study_info.get("sequence_number", "0000").zfill(4)
    app_num = study_info.get("application_number", "new").replace("/", "-")
    pkg_name = f"ectd_{app_num}_{seq}_{today}"

    pkg_dir = Path(output_dir) / pkg_name
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # Create module subdirectories
    for mod_num in _ECTD_MODULES:
        (pkg_dir / f"m{mod_num}").mkdir(exist_ok=True)

    # Copy / placeholder documents into module directories
    placed_docs = []
    for doc in study_info.get("documents", []):
        src = Path(doc.get("file_path", ""))
        mod = str(doc.get("module", "1"))
        section = doc.get("section", "1.0")
        target_dir = pkg_dir / f"m{mod}"

        if src.exists():
            import shutil
            dest = target_dir / src.name
            shutil.copy2(src, dest)
            placed_docs.append((mod, section, doc.get("title", src.stem), dest.name))
        else:
            # Create a placeholder text file
            placeholder_name = f"{section.replace('.', '_')}_{doc.get('title', 'document').replace(' ', '_')}.txt"
            (target_dir / placeholder_name).write_text(
                f"PLACEHOLDER: {doc.get('title', '')}\nModule: {mod} | Section: {section}\n",
                encoding="utf-8",
            )
            placed_docs.append((mod, section, doc.get("title", ""), placeholder_name))

    # Build eCTD index.xml backbone
    index_xml = _build_index_xml(study_info, placed_docs)
    (pkg_dir / "index.xml").write_text(index_xml, encoding="utf-8")

    # Compute MD5 checksums
    md5_xml = _build_md5_index(pkg_dir)
    (pkg_dir / "index-md5.xml").write_text(md5_xml, encoding="utf-8")

    logger.info("eCTD package built at %s", pkg_dir)
    return pkg_dir


def _build_index_xml(study_info: dict, documents: list) -> str:
    """Build the eCTD index.xml backbone document."""
    etree = _etree
    _XSI = "http://www.w3.org/2001/XMLSchema-instance"
    NSMAP = {None: "urn:hl7-org:v3", "xsi": _XSI}
    root = etree.Element("ich-ectd", nsmap=NSMAP)
    root.set(f"{{{_XSI}}}schemaLocation", "urn:hl7-org:v3 ectd-2-0.xsd")

    # Header
    header = etree.SubElement(root, "header")
    etree.SubElement(header, "dossier-identifier").text = study_info.get("application_number", "")
    etree.SubElement(header, "dossier-type").text = study_info.get("application_type", "IND")
    etree.SubElement(header, "sequence-number").text = study_info.get("sequence_number", "0000")
    etree.SubElement(header, "sponsor-name").text = study_info.get("sponsor_name", "")
    etree.SubElement(header, "applicant-name").text = study_info.get("sponsor_name", "")
    etree.SubElement(header, "drug-name").text = study_info.get("drug_name", "")
    etree.SubElement(header, "indication").text = study_info.get("indication", "")
    etree.SubElement(header, "created-date").text = date.today().isoformat()

    # Table of contents
    toc = etree.SubElement(root, "table-of-contents")
    for mod_num, section, title, filename in documents:
        doc_el = etree.SubElement(toc, "document")
        etree.SubElement(doc_el, "module").text = mod_num
        etree.SubElement(doc_el, "section").text = section
        etree.SubElement(doc_el, "title").text = title
        etree.SubElement(doc_el, "file").text = f"m{mod_num}/{filename}"
        etree.SubElement(doc_el, "operation").text = "new"

    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8").decode("utf-8")


def _build_md5_index(pkg_dir: Path) -> str:
    """Build index-md5.xml with MD5 checksums for all files in the package."""
    etree = _etree
    root = etree.Element("md5-index")
    for file_path in sorted(pkg_dir.rglob("*")):
        if file_path.is_file() and file_path.name not in ("index-md5.xml",):
            rel = file_path.relative_to(pkg_dir)
            md5 = hashlib.md5(file_path.read_bytes()).hexdigest()
            entry = etree.SubElement(root, "file")
            entry.set("path", str(rel).replace("\\", "/"))
            entry.set("md5", md5)

    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8").decode("utf-8")


def zip_ectd_package(pkg_dir: Path) -> Path:
    """Zip the eCTD package directory for upload."""
    zip_path = pkg_dir.parent / f"{pkg_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(pkg_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(pkg_dir.parent))
    logger.info("eCTD package zipped: %s", zip_path)
    return zip_path


def get_esg_token(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> str:
    """
    Obtain an OAuth 2.0 access token from FDA ESG NextGen.

    Args:
        client_id:     from FDA Unified Submission Portal (defaults to FDA_CLIENT_ID)
        client_secret: (defaults to FDA_CLIENT_SECRET)

    Returns:
        Bearer token string.

    Raises:
        ValueError:  if credentials are not configured
        RuntimeError: if token request fails
    """
    cid = client_id or settings.fda_client_id
    csec = client_secret or settings.fda_client_secret

    if not cid or not csec:
        raise ValueError(
            "FDA credentials required. Set FDA_CLIENT_ID and FDA_CLIENT_SECRET in .env"
        )

    resp = requests.post(
        ESG_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": csec,
        },
        timeout=15,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"ESG token request failed [{resp.status_code}]: {resp.text[:300]}")

    token = resp.json().get("access_token", "")
    logger.info("FDA ESG NextGen token obtained.")
    return token


def upload_to_esg(
    zip_path: Path,
    token: str,
    application_type: str = "IND",
    application_number: str = "",
) -> str:
    """
    Upload a zipped eCTD package to FDA ESG NextGen.

    Steps:
      1. POST /credentials/api to get a submission ID + presigned S3 URL
      2. PUT the zip file to the presigned URL

    Args:
        zip_path:         path to the zipped eCTD package
        token:            bearer token from get_esg_token()
        application_type: "IND", "NDA", "BLA", etc.
        application_number: existing application number (empty for new submission)

    Returns:
        ESG submission ID string.
    """
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    payload = {
        "applicationType": application_type,
        "applicationNumber": application_number,
        "fileName": zip_path.name,
    }

    cred_resp = requests.post(
        ESG_CREDENTIALS_URL, json=payload, headers=headers, timeout=15
    )
    if cred_resp.status_code != 200:
        raise RuntimeError(
            f"ESG credentials request failed [{cred_resp.status_code}]: {cred_resp.text[:300]}"
        )

    cred_data = cred_resp.json()
    submission_id: str = cred_data["submissionId"]
    s3_url: str = cred_data["presignedUrl"]
    s3_fields: dict = cred_data.get("fields", {})

    # Upload to presigned S3 URL
    with open(zip_path, "rb") as f:
        if s3_fields:
            # Multipart form upload (some ESG configurations)
            upload_resp = requests.post(
                s3_url,
                data=s3_fields,
                files={"file": (zip_path.name, f, "application/zip")},
                timeout=120,
            )
        else:
            upload_resp = requests.put(
                s3_url,
                data=f,
                headers={"Content-Type": "application/zip"},
                timeout=120,
            )

    if upload_resp.status_code not in (200, 201, 204):
        raise RuntimeError(
            f"S3 upload failed [{upload_resp.status_code}]: {upload_resp.text[:300]}"
        )

    logger.info("eCTD package uploaded to ESG NextGen. Submission ID: %s", submission_id)
    return submission_id


def check_submission_status(
    submission_id: str,
    token: str,
) -> dict:
    """
    Poll FDA ESG NextGen for submission processing status.

    Returns:
        Status dict with keys: submission_id, status, message, timestamp.
    """
    url = ESG_STATUS_URL.format(submission_id=submission_id)
    headers = {"Authorization": f"Bearer {token}"}

    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Status check failed [{resp.status_code}]: {resp.text[:300]}"
        )

    data = resp.json()
    logger.info(
        "ESG submission %s status: %s", submission_id, data.get("status", "unknown")
    )
    return data
