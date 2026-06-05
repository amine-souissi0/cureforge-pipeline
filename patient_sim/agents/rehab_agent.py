"""Agent 5 — Physical Rehabilitation Planner (right arm + right leg) — bilingual EN/RU."""
from __future__ import annotations
from .base import groq_call

SYSTEM = """You are the Physical Rehabilitation Agent for CureForge AI.
Design a personalized physiotherapy protocol for right-sided hemiparesis following left MCA ischemic stroke.

RULES:
1. All output BOTH in English AND Russian
2. Base exercises on current NIHSS, Rankin, Rivermead scores
3. Respect: age 83, hip arthroplasty (left), left foot amputation, CKD G2
4. Specify frequency, duration, progression criteria
5. All therapist-dependent exercises labeled "requires physiotherapist"
6. Include home exercises family can perform

Return JSON:
{
  "right_arm_protocol": {
    "current_status_en": "string", "current_status_ru": "string",
    "goal_en": "string", "goal_ru": "string",
    "exercises": [
      {"name_en":"str","name_ru":"str","description_en":"str","description_ru":"str",
       "frequency":"str","duration":"str","level":"passive|active_assisted|active","requires_physio":true}
    ],
    "contraindications_en": "string", "contraindications_ru": "string"
  },
  "right_leg_protocol": {
    "current_status_en": "string", "current_status_ru": "string",
    "goal_en": "string", "goal_ru": "string",
    "exercises": [
      {"name_en":"str","name_ru":"str","description_en":"str","description_ru":"str",
       "frequency":"str","duration":"str","level":"passive|active_assisted|active","requires_physio":true}
    ],
    "balance_training_en": "string", "balance_training_ru": "string",
    "gait_retraining_en": "string", "gait_retraining_ru": "string"
  },
  "speech_motor_integration": {
    "approach_en": "string", "approach_ru": "string"
  },
  "weekly_schedule": {
    "monday_en": "string", "monday_ru": "string",
    "routine_en": "string", "routine_ru": "string"
  },
  "family_instructions": {
    "en": ["list of 5 instructions"],
    "ru": ["5 инструкций на русском"]
  },
  "progress_milestones": [
    {"week": 1, "target_en": "str", "target_ru": "str"}
  ],
  "rehab_centers": {
    "moscow_options_en": "string",
    "moscow_options_ru": "string"
  }
}"""


def run(patient_summary: str, cds_result: dict) -> dict:
    user = f"""Patient:
{patient_summary}

Clinical context: {str(cds_result)[:800]}

Design bilingual right-arm + right-leg rehabilitation protocol.
Current: Rankin 5, Rivermead 2, NIHSS 12 — severe disability, early recovery phase.
Right arm: paresis (makes fist, limited active movement)
Right leg: nearly recovered (active movements present)
Left foot amputated. Hip arthroplasty left side.
Age 83 — conservative intensity, fall prevention priority."""
    return groq_call(SYSTEM, user, json_mode=True, max_tokens=2500)
