"""
DUA Agent — Data Use Agreement drafting + dataset descriptor generation.

What this does automatically:
  - Drafts a Data Use Agreement using GPT-4 based on dataset and requester info
  - Generates a machine-readable Frictionless Data descriptor (datapackage.json)
  - Produces a formal data request letter for closed-source dataset owners

What still requires human action:
  - DUAs are legal instruments — must be reviewed by institutional legal/IRB
  - Signatures and institutional authorization are always required
  - Data custodian (the provider) must independently agree to the terms

NOTE: This agent produces DRAFT documents for legal review only.
      Never execute or distribute DUAs without institutional approval.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from openai import OpenAI

from config.settings import settings

logger = logging.getLogger(__name__)

_client = OpenAI(api_key=settings.openai_api_key)

_DUA_SYSTEM_PROMPT = """\
You are an expert research compliance officer drafting a Data Use Agreement (DUA)
for an academic/biotech research institution.

Write a formal DUA covering:
1. PARTIES — Data Provider and Data Recipient (full legal names, addresses)
2. PURPOSE — specific, limited research purpose
3. DATA DESCRIPTION — what data, format, variables, time period
4. PERMITTED USES — exactly what the recipient may do with the data
5. PROHIBITED USES — what is explicitly forbidden
6. DATA SECURITY — storage, encryption, access controls, incident response
7. PUBLICATION RIGHTS — how findings may be published; acknowledgement required
8. TERM AND TERMINATION — duration, renewal, what happens to data at end
9. CONFIDENTIALITY — obligations of recipient researchers
10. LIABILITY AND INDEMNIFICATION — standard limitation of liability clause
11. GOVERNING LAW — jurisdiction (default: Delaware, USA)
12. SIGNATURES — signature blocks for authorized representatives

Use formal legal language. Note: THIS IS A DRAFT — requires legal review before execution.\
"""

_REQUEST_LETTER_SYSTEM = """\
You are a senior researcher writing a formal data access request letter to a
data custodian. The letter should:
  1. Introduce the requester and institution
  2. Describe the research purpose concisely (2–3 sentences)
  3. Specify exactly what data is needed and why
  4. Describe data security measures in place
  5. Offer to sign a DUA
  6. Include contact information and timeline
Keep under 500 words. Formal, professional tone.\
"""


def draft_dua(
    dataset_info: dict,
    requester_info: dict,
    provider_info: dict,
    model: Optional[str] = None,
) -> str:
    """
    Draft a Data Use Agreement using GPT-4.

    Args:
        dataset_info:  dict with keys: name, description, variables, format,
                       record_count, time_period, sensitivity_level
        requester_info: dict with keys: institution, pi_name, pi_title,
                        pi_email, address, irb_number (optional)
        provider_info:  dict with keys: organization, contact_name,
                        contact_email, address
        model:          override LLM model

    Returns:
        Draft DUA as a formatted string.
    """
    user_prompt = f"""
DATA PROVIDER:
  Organization: {provider_info.get('organization', '')}
  Contact: {provider_info.get('contact_name', '')} <{provider_info.get('contact_email', '')}>
  Address: {provider_info.get('address', '')}

DATA RECIPIENT:
  Institution: {requester_info.get('institution', '')}
  PI: {requester_info.get('pi_name', '')} ({requester_info.get('pi_title', '')})
  Email: {requester_info.get('pi_email', '')}
  Address: {requester_info.get('address', '')}
  IRB Number: {requester_info.get('irb_number', 'Pending')}

DATASET:
  Name: {dataset_info.get('name', '')}
  Description: {dataset_info.get('description', '')}
  Variables: {dataset_info.get('variables', '')}
  Format: {dataset_info.get('format', '')}
  Records: {dataset_info.get('record_count', '')}
  Time Period: {dataset_info.get('time_period', '')}
  Sensitivity: {dataset_info.get('sensitivity_level', 'Sensitive')}

RESEARCH PURPOSE:
  {dataset_info.get('research_purpose', '')}
"""

    response = _client.chat.completions.create(
        model=model or settings.openai_model,
        messages=[
            {"role": "system", "content": _DUA_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=2000,
    )

    dua = response.choices[0].message.content.strip()
    logger.info(
        "DUA draft generated for dataset '%s'", dataset_info.get("name", "")
    )
    return dua


def draft_request_letter(
    dataset_info: dict,
    requester_info: dict,
    provider_info: dict,
    model: Optional[str] = None,
) -> str:
    """
    Draft a formal data access request letter to send to a data custodian.

    Returns:
        Formatted request letter as a string.
    """
    user_prompt = (
        f"Requester: {requester_info.get('pi_name', '')} at "
        f"{requester_info.get('institution', '')}\n"
        f"Provider/Custodian: {provider_info.get('organization', '')}\n"
        f"Dataset: {dataset_info.get('name', '')} — {dataset_info.get('description', '')}\n"
        f"Research Purpose: {dataset_info.get('research_purpose', '')}\n"
        f"Data Needed: {dataset_info.get('variables', '')}\n"
        f"Security Measures: {requester_info.get('security_measures', 'secure institutional server, IRB-approved protocol')}\n"
        f"Timeline: {dataset_info.get('timeline', 'as soon as possible')}\n"
    )

    response = _client.chat.completions.create(
        model=model or settings.openai_model,
        messages=[
            {"role": "system", "content": _REQUEST_LETTER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=700,
    )

    letter = response.choices[0].message.content.strip()
    logger.info("Data request letter drafted for '%s'", dataset_info.get("name", ""))
    return letter


def build_data_descriptor(
    dataset_info: dict,
    schema: Optional[list[dict]] = None,
) -> dict:
    """
    Generate a Frictionless Data-compatible datapackage.json descriptor.

    This formally documents the dataset structure for the DUA and for
    reproducibility purposes.

    Args:
        dataset_info: dict with keys: name, description, variables, format, license
        schema:       list of field dicts: {name, type, description, constraints}

    Returns:
        datapackage dict (can be serialized to JSON).
    """
    fields = []
    if schema:
        for field in schema:
            f = {
                "name": field.get("name", ""),
                "type": field.get("type", "string"),
                "description": field.get("description", ""),
            }
            if field.get("constraints"):
                f["constraints"] = field["constraints"]
            fields.append(f)
    else:
        # Build basic fields from variables string if no schema provided
        for var in dataset_info.get("variables", "").split(","):
            var = var.strip()
            if var:
                fields.append({"name": var, "type": "string", "description": ""})

    safe_name = dataset_info.get("name", "dataset").lower().replace(" ", "-")

    descriptor = {
        "name": safe_name,
        "title": dataset_info.get("name", ""),
        "description": dataset_info.get("description", ""),
        "licenses": [{"name": dataset_info.get("license", "proprietary")}],
        "resources": [
            {
                "name": safe_name,
                "path": f"data/{safe_name}.csv",
                "format": dataset_info.get("format", "CSV"),
                "mediatype": "text/csv",
                "schema": {"fields": fields},
            }
        ],
        "keywords": dataset_info.get("keywords", []),
        "temporal_coverage": dataset_info.get("time_period", ""),
        "sensitivity": dataset_info.get("sensitivity_level", "Sensitive"),
        "record_count": dataset_info.get("record_count", ""),
    }

    logger.info("Data descriptor built for '%s'", dataset_info.get("name", ""))
    return descriptor


def save_dua_package(
    dua_text: str,
    request_letter: str,
    descriptor: dict,
    dataset_name: str,
    output_dir: str = "output/dua",
) -> Path:
    """
    Save all DUA-related documents to a package directory.

    Returns:
        Path to the output directory.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    safe_name = dataset_name.lower().replace(" ", "_")[:40]

    disclaimer = (
        "⚠️  DRAFT FOR LEGAL REVIEW ONLY — Do not execute without institutional approval.\n\n"
    )

    (out / f"{safe_name}_dua_draft.md").write_text(
        disclaimer + dua_text, encoding="utf-8"
    )
    (out / f"{safe_name}_request_letter.md").write_text(
        request_letter, encoding="utf-8"
    )
    (out / "datapackage.json").write_text(
        json.dumps(descriptor, indent=2), encoding="utf-8"
    )

    logger.info("DUA package saved to %s", out)
    return out
