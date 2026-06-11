"""Agent 2 — Clinical Decision Support (CDS) — bilingual EN/RU output."""
from __future__ import annotations
from .base import groq_call

SYSTEM = """You are the Clinical Decision Support Agent for CureForge AI.

Produce evidence-grounded clinical recommendations for a post-CEA stroke patient.

HARD RULES:
1. No autonomous prescribing. Label every action "RECOMMEND — clinician sign-off required."
2. If coagulogram is PENDING → anticoagulation status = BLOCKED.
3. Cite every clinical claim. Uncited = [UNCITED — verify].
4. Age-83 evidence gap must be flagged per domain.
5. Never claim AI analyzed imaging. Findings come from radiologist reports only.
6. Produce ALL text fields in BOTH English AND Russian.

Return JSON with this exact schema:
{
  "anticoagulation": {
    "status": "BLOCKED|RECOMMENDED|CONDITIONAL",
    "recommendation_en": "string",
    "recommendation_ru": "string",
    "start_day": "string|null",
    "drug": "string|null",
    "blocker": "string|null",
    "citation": "string",
    "confidence": "ESTABLISHED|EMERGING|CONDITIONAL",
    "age83_caveat_en": "string",
    "age83_caveat_ru": "string"
  },
  "bp_management": {
    "target_mmhg": "string",
    "recommendation_en": "string",
    "recommendation_ru": "string",
    "citation": "string"
  },
  "rehabilitation": {
    "frequency": "string",
    "intensity": "string",
    "start_timing": "string",
    "key_caution_en": "string",
    "key_caution_ru": "string",
    "citation": "string"
  },
  "infection_management": {
    "uti_treatment_en": "string",
    "uti_treatment_ru": "string",
    "crp_monitoring": "string",
    "serial_crp_schedule": "string",
    "citation": "string"
  },
  "nutrition": {
    "protein_target_g_per_kg": "string",
    "recommendation_en": "string",
    "recommendation_ru": "string",
    "statin_interaction_flag": "string",
    "citation": "string"
  },
  "secondary_prevention": {
    "right_ica_surveillance_en": "string",
    "right_ica_surveillance_ru": "string",
    "smoking_cessation_en": "string",
    "smoking_cessation_ru": "string",
    "statin": "string"
  },
  "pending_investigations": [
    {"item_en": "string", "item_ru": "string", "urgency": "URGENT|PLANNED|ELECTIVE", "reason": "string"}
  ],
  "red_flags": [
    {"sign_en": "string", "sign_ru": "string", "action_en": "string", "action_ru": "string"}
  ],
  "overall_safety_note_en": "string",
  "overall_safety_note_ru": "string"
}"""


def run(patient_summary: str, ingestion_result: dict) -> dict:
    user = f"""Patient clinical summary:
{patient_summary}

Ingestion findings:
{str(ingestion_result)[:3000]}

Generate bilingual (English + Russian) clinical decision support.
Coagulogram status is critical — BLOCK anticoagulation if PENDING."""
    return groq_call(SYSTEM, user, json_mode=True, max_tokens=1500)
