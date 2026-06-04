"""Agent 4 — Bilingual Report Generator (EN for investors, RU for doctors)."""
from __future__ import annotations
from datetime import datetime
from .base import groq_call

SYSTEM_EN = """You are the Report Generator for CureForge AI — English version for investors.

Write a concise, professional clinical summary for an international audience (investors, board).
- No medical jargon — translate all clinical terms
- Emphasise the AI system capabilities and what was demonstrated
- Show: what the patient's condition is, what the AI found, what was recommended
- Keep it 400-600 words max
- Structure: Executive Summary → Clinical Status → AI Findings → Recommendations → Next Steps
- Include a CureForge system note at the end showing this was AI-generated with human oversight

Return clean Markdown."""

SYSTEM_RU = """Вы — генератор клинического отчёта CureForge AI — версия на русском языке для врачей.

Напишите полный клинический отчёт для медицинского персонала ГКБ им. Кончаловского.
- Используйте стандартную медицинскую терминологию на русском языке
- Включите все клинически значимые данные
- Структура: Краткое резюме → Неврологический статус → Данные визуализации → КДС → Рекомендации → Открытые вопросы → Дальнейшие шаги
- Укажите все БЛОКИРУЮЩИЕ факторы (коагулограмма, МРТ, GUSS)
- Отметьте каждую рекомендацию: "требует подтверждения врача"

Верните чистый Markdown на русском языке."""


def run(patient_summary: str, ingestion: dict, cds: dict, recovery: dict,
        audit_findings: str = "") -> tuple:
    """Returns (english_report, russian_report) as a tuple of Markdown strings."""
    now = datetime.utcnow().strftime("%d %B %Y %H:%M UTC")

    context = f"""Patient summary:
{patient_summary}

CDS findings (key points):
Anticoagulation: {cds.get('anticoagulation', {}).get('status', '?')} — {cds.get('anticoagulation', {}).get('recommendation_en', cds.get('anticoagulation', {}).get('recommendation', '?'))}
BP target: {cds.get('bp_management', {}).get('target_mmhg', '?')}
Red flags count: {len(cds.get('red_flags', []))}

Recovery plan highlights:
{str(recovery.get('priority_actions', []))[:500]}

Audit notes:
{audit_findings[:500]}

Report date: {now}"""

    # Generate English report
    en_report = groq_call(SYSTEM_EN, context, json_mode=False, max_tokens=2000, temperature=0.2)

    # Generate Russian report
    ru_report = groq_call(SYSTEM_RU, context, json_mode=False, max_tokens=2500, temperature=0.2)

    return en_report, ru_report


def run_single(patient_summary, ingestion, cds, recovery, audit_findings="") -> str:
    """Backward-compat: returns combined EN+RU report."""
    en, ru = run(patient_summary, ingestion, cds, recovery, audit_findings)
    return f"# 🇬🇧 English Report — For Investors\n\n{en}\n\n---\n\n# 🇷🇺 Отчёт на русском — Для врачей\n\n{ru}"
