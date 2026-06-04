"""
Agent 1 — Ingestion Agent (ING)

Input : Raw clinical documents (DOCX text) + DICOM metadata
Output: Validated patient model JSON with per-finding provenance

Guardrail: NEVER invents a finding. Every field is extracted from a named source
document. If a value is not in the source, the field is null with a note.
"""
from __future__ import annotations
import json
from pathlib import Path
from .base import groq_call

DOCS_DIR = Path(__file__).parent.parent / "data"

SYSTEM = """You are a medical data ingestion agent for CureForge AI.

Your job: extract structured clinical data from patient documents and return valid JSON.

RULES:
1. ONLY extract information explicitly stated in the provided documents.
2. For each extracted value, record which document it came from (provenance).
3. If a value is NOT in the documents, set it to null and note "not in documents".
4. NEVER infer, calculate, or invent clinical values.
5. Flag any inconsistencies found between documents.

Return JSON matching this schema exactly:
{
  "patient_id": "string",
  "extraction_date": "YYYY-MM-DD",
  "provenance_notes": ["list of source notes"],
  "inconsistencies": ["list of any cross-document conflicts found"],
  "missing_critical": ["list of clinically critical missing values"],
  "stroke": {
    "type": "string|null",
    "date": "YYYY-MM-DD|null",
    "mechanism": "string|null",
    "infarct_location": "string|null",
    "infarct_size": "string|null",
    "aspects_score": "integer|null",
    "aspects_source": "string|null",
    "nihss_scores": [{"date": "string", "score": "integer", "note": "string"}]
  },
  "deficits": {
    "aphasia_type": "string|null",
    "comprehension": "string|null",
    "right_arm": "string|null",
    "right_leg": "string|null",
    "swallowing": "string|null",
    "swallowing_formal_test": "string|null",
    "facial_asymmetry": "string|null"
  },
  "key_labs": {
    "crp_mg_l": "float|null",
    "egfr": "float|null",
    "uti_active": "boolean|null",
    "coagulogram": "string|null"
  },
  "imaging_available": {
    "brain_ct": "boolean",
    "brain_ct_date": "string|null",
    "mri": "boolean",
    "neck_cta": "boolean",
    "neck_cta_date": "string|null",
    "note": "string"
  },
  "anticoagulation_open_questions": ["list of unresolved questions"],
  "confidence_flags": {"field_name": "HIGH|MEDIUM|LOW|UNSUPPORTED"}
}"""


def _load_docs() -> str:
    """Load all available clinical text documents."""
    parts = []
    for txt in sorted(DOCS_DIR.glob("*.txt")):
        text = txt.read_text(errors='replace')[:3000]
        parts.append(f"=== {txt.stem.upper()} ===\n{text}\n")
    return "\n".join(parts)


def run(patient_summary: str = "") -> dict:
    """Run ingestion agent on available clinical documents."""
    docs = _load_docs()
    user = f"""Extract all clinical data from these patient documents:

{docs[:12000]}

Return the complete JSON schema with all fields populated or null with provenance."""

    result = groq_call(SYSTEM, user, json_mode=True, max_tokens=3000)
    return result
