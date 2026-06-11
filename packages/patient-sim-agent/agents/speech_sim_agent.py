"""Agent 7 — Speech Recovery Simulation Model (RU/EN/SW) — bilingual."""
from __future__ import annotations
from .base import groq_call


def get_simulation_spec() -> dict:
    """Static design of the speech recognition / recovery / guidance simulation."""
    return {
        "status": "DESIGN_PHASE",
        "description_en": "Speech recovery simulation across Russian/English/Swahili — predicts trajectory and guides therapy",
        "description_ru": "Симуляция восстановления речи (русский/английский/суахили) — прогноз и руководство терапией",
        "pipeline": {
            "input": "Daily speech recordings (audio+video, 3 langs) from Speech Recording Protocol",
            "recognition_models": [
                "Whisper-large-v3 (multilingual ASR: RU/EN/SW)",
                "Articulation scorer (dysarthria — syllable rate, clarity)",
                "Aphasia marker detector (pauses, word-finding latency)"
            ],
            "simulation_engine": [
                "Per-language recovery curve fit (logistic growth model)",
                "Cross-language transfer model (does RU recovery pull EN/SW?)",
                "Monte-Carlo NIHSS-language-subscore projection D30/D60/D90"
            ],
            "output": [
                "Intelligibility score per language (0-100) per day",
                "Predicted plateau + weeks-to-milestone",
                "Next-session difficulty auto-adjust (adaptive therapy)",
                "Red-flag: regression alert to clinician"
            ]
        },
        "languages": {
            "russian": {"priority": 1, "rationale_en": "Native — fastest recovery, anchor language",
                        "rationale_ru": "Родной — самое быстрое восстановление, опорный язык"},
            "english": {"priority": 2, "rationale_en": "Second language — moderate recovery",
                        "rationale_ru": "Второй язык — умеренное восстановление"},
            "swahili": {"priority": 3, "rationale_en": "27y immersion — emotional/long-term memory, may resist loss",
                        "rationale_ru": "27 лет погружения — эмоциональная/долговременная память, устойчив"}
        },
        "guidance_loop_en": "Each day: record → score → simulate → adjust tomorrow's word list to the patient's edge of ability (not too easy, not too hard).",
        "guidance_loop_ru": "Каждый день: запись → оценка → симуляция → подбор завтрашнего списка слов на грани возможностей пациента.",
        "milestones": [
            {"week": 2, "target_en": "Sustained vowels stable, counting 1-10 RU", "target_ru": "Гласные стабильны, счёт 1-10 рус"},
            {"week": 6, "target_en": "5-word naming RU >80%, EN emerging", "target_ru": "Называние 5 слов рус >80%, англ появляется"},
            {"week": 12, "target_en": "Short sentences RU, single words EN/SW", "target_ru": "Короткие фразы рус, отдельные слова англ/суахили"}
        ],
        "where_it_ends_en": "Goal endpoint: functional communication in Russian (daily needs) by ~month 3, with EN/SW as bonus. The simulation continuously forecasts the date this is reached and flags if the patient falls off the predicted curve.",
        "where_it_ends_ru": "Конечная цель: функциональное общение на русском (бытовые нужды) к ~3 месяцу, англ/суахили — бонус. Симуляция постоянно прогнозирует дату достижения и сигнализирует при отклонении от кривой."
    }


def run(patient_summary: str, recovery_result: dict) -> dict:
    spec = get_simulation_spec()
    user = f"""Patient: {patient_summary[:500]}
Trilingual (Russian native / English / Swahili). Complex motor aphasia + dysarthria.
Generate a 7-day adaptive speech therapy starting plan, with specific RU/EN/SW word targets per day.
Return JSON with a 'week1_plan' array of 7 day objects (day, russian_task, english_task, swahili_task, difficulty)."""
    plan = groq_call(
        "You are a trilingual speech therapy planner. Return JSON only.",
        user, json_mode=True, max_tokens=1200
    )
    spec["llm_week1_plan"] = plan
    return spec
