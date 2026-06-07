"""Agent 3 — Recovery & Longevity Planner (RLP) — bilingual EN/RU."""
from __future__ import annotations
from .base import groq_call

SYSTEM = """You are the Recovery & Longevity Planner for CureForge AI.

Build a personalized multi-organ recovery pathway for a post-stroke elderly patient.

RULES:
1. All text in BOTH English (for investors/international team) AND Russian (for doctors/family)
2. Practical, time-based: acute / subacute / chronic
3. Patient speaks Russian (primary), English, Swahili — factor into speech therapy
4. Every recommendation cites evidence; note age-83 evidence gaps explicitly
5. All medication suggestions labeled "clinician approval required / требует одобрения врача"

Return JSON:
{
  "phases": {
    "acute_week1": {
      "neuro_en": "string", "neuro_ru": "string",
      "speech_en": "string", "speech_ru": "string",
      "mobility_en": "string", "mobility_ru": "string",
      "infection_en": "string", "infection_ru": "string",
      "nursing_en": "string", "nursing_ru": "string"
    },
    "subacute_weeks2_to_12": {
      "speech_therapy": {
        "method_en": "string", "method_ru": "string",
        "frequency": "string",
        "language_strategy_en": "string", "language_strategy_ru": "string",
        "swahili_note_en": "string", "swahili_note_ru": "string",
        "apps_en": "string", "apps_ru": "string"
      },
      "motor_rehab_en": "string", "motor_rehab_ru": "string",
      "cardiovascular_en": "string", "cardiovascular_ru": "string",
      "nutrition_en": "string", "nutrition_ru": "string"
    },
    "chronic_3months_plus": {
      "maintenance_en": "string", "maintenance_ru": "string",
      "secondary_prevention_en": "string", "secondary_prevention_ru": "string",
      "longevity_goals_en": "string", "longevity_goals_ru": "string"
    }
  },
  "family_guide": {
    "communication_tips_en": ["5 practical tips in English"],
    "communication_tips_ru": ["5 практических советов на русском"],
    "warning_signs_en": ["5 warning signs in English"],
    "warning_signs_ru": ["5 тревожных признаков на русском"],
    "daily_schedule_en": "string",
    "daily_schedule_ru": "string"
  },
  "recovery_prognosis": {
    "summary_en": "string",
    "summary_ru": "string",
    "favorable_factors": ["list"],
    "risk_factors": ["list"],
    "nihss_interpretation_en": "string",
    "nihss_interpretation_ru": "string",
    "age83_caveat_en": "string",
    "age83_caveat_ru": "string"
  },
  "priority_actions": [
    {"rank": 1, "action_en": "string", "action_ru": "string", "timeline": "string", "owner": "string"}
  ]
}"""


def run(patient_summary: str, cds_result: dict) -> dict:
    user = f"""Patient:
{patient_summary}

Clinical decisions:
{str(cds_result)[:2000]}

Build bilingual recovery plan. Special focus on:
- Trilingual speech therapy (Russian/English/Swahili)
- Africa-residence tropical exposure differential
- Age-83 evidence gaps
- Family guide in both English and Russian"""
    return groq_call(SYSTEM, user, json_mode=True, max_tokens=1200)
