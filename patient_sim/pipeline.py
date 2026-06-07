"""
CureForge Patient Simulation Pipeline — Orchestrator

4-agent pipeline with bilingual (EN/RU) output and graceful fallback.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from patient_sim.models.patient import PatientModel
from patient_sim.agents import ingestion_agent, cds_agent, recovery_agent, report_agent, rehab_agent, vision_agent

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"

# Filesystem: try app dir, fall back to /tmp (Streamlit Cloud is read-only)
_APP_REPORTS = Path(__file__).parent / "reports"
_TMP_REPORTS = Path("/tmp") / "cureforge_reports"
_TMP_REPORTS.mkdir(exist_ok=True)

try:
    _APP_REPORTS.mkdir(exist_ok=True)
    (_APP_REPORTS / ".wt").write_text("ok")
    (_APP_REPORTS / ".wt").unlink()
    REPORTS_DIR = _APP_REPORTS
except (PermissionError, OSError):
    REPORTS_DIR = _TMP_REPORTS

AUDIT_FINDINGS = """
IMAGING — ALL 3 ZIPs PROCESSED:
ZIP1 (5426422154.zip): NECK CTA, 2060 slices, 27.05.2026 — carotid post-CEA assessment.
ZIP2 (5426422151.zip): BRAIN CT Day 1, 347 slices, GE Revolution Maxima, 27.05.2026, KVP 120.
ZIP3 (5426422543.zip): BRAIN CT Day 2, 323 slices, GE Revolution Maxima, 28.05.2026, KVP 80 (low-dose follow-up, C150/W1500).
ASPECTS 8 — left frontal cortex M4-M5 — no hemorrhage — no edema — from human radiologist 28.05.2026 report (NOT AI-computed).
Day 2 CT (ZIP3) confirms: no hemorrhagic transformation, no malignant MCA edema, infarct zone stabilising.
MRI: not yet provided.

COAGULOGRAM: Pending — anticoagulation BLOCKED until received.
BAT bilingual aphasia test: not done. GUSS swallowing screen: not formally documented.
Eosinophil count + Strongyloides serology: absent (Africa differential pending).
"""


def _progress(step: str, total: int, current: int) -> dict:
    return {
        "step": step,
        "progress_pct": int(current / total * 100),
        "timestamp": datetime.utcnow().isoformat(),
    }


def run_analysis(progress_callback=None, coagulogram: Optional[str] = None) -> dict:
    start = time.time()

    def _cb(step, pct):
        if progress_callback:
            progress_callback(_progress(step, 100, pct))
        logger.info("[%d%%] %s", pct, step)

    _cb("Loading patient model", 5)
    patient = PatientModel()
    if coagulogram:
        patient.comorbidities.coagulogram_result = coagulogram
    summary = patient.to_clinical_summary()

    # Agent 1 — Ingestion (uses lighter model to save rate-limit budget)
    _cb("Agent 1/4 — Ingestion: parsing clinical documents", 15)
    ingestion = ingestion_agent.run(summary)
    patient.outputs.ingestion_complete = isinstance(ingestion, dict) and "error" not in ingestion
    patient.outputs.ingestion_result = ingestion
    _cb("Ingestion complete", 30)
    time.sleep(8)  # Groq free-tier: avoid 429 between sequential calls

    # Agent 2 — CDS
    _cb("Agent 2/4 — Clinical Decision Support", 35)
    cds = cds_agent.run(summary, ingestion)
    patient.outputs.cds_complete = isinstance(cds, dict) and "error" not in cds
    patient.outputs.cds_result = cds
    _cb("CDS complete", 55)

    time.sleep(8)  # Groq rate-limit buffer

    # Agent 3 — Recovery
    _cb("Agent 3/4 — Recovery & Longevity Planner", 60)
    recovery = recovery_agent.run(summary, cds)
    patient.outputs.recovery_complete = isinstance(recovery, dict) and "error" not in recovery
    # Persist the recovery plan itself so the Recovery tab works on cold cache load
    if isinstance(recovery, dict):
        patient.outputs.recovery_result = dict(recovery)
    _cb("Recovery plan complete", 75)

    time.sleep(8)  # Groq rate-limit buffer

    # Agent 5 — Physical Rehabilitation
    _cb("Agent 5/6 — Physical Rehabilitation Protocol", 82)
    rehab = rehab_agent.run(summary, cds)
    patient.outputs.recovery_result["rehab"] = rehab
    _cb("Rehab protocol complete", 86)

    time.sleep(5)

    # Agent 6 — Computer Vision (design spec + recommendations)
    _cb("Agent 6/6 — Computer Vision Movement Tracker", 88)
    cv = vision_agent.run(summary, rehab)
    patient.outputs.recovery_result["cv"] = cv
    _cb("CV agent complete", 90)

    time.sleep(5)

    # Agent 4 — Bilingual Report
    _cb("Agent 4/4 — Generating bilingual report (EN + RU)", 91)
    try:
        en_report, ru_report = report_agent.run(summary, ingestion, cds, recovery, AUDIT_FINDINGS)
        combined = f"# 🇬🇧 English Report — For Investors\n\n{en_report}\n\n---\n\n# 🇷🇺 Отчёт — Для врачей\n\n{ru_report}"
    except Exception as e:
        combined = report_agent.run_single(summary, ingestion, cds, recovery, AUDIT_FINDINGS)
        en_report = combined
        ru_report = ""

    patient.outputs.report_complete = bool(combined and len(combined) > 100)
    patient.outputs.report_markdown = combined
    patient.outputs.report_markdown_ru = ru_report
    _cb("Report generated", 97)

    # Persist
    duration = round(time.time() - start, 1)
    patient.outputs.run_timestamp = datetime.utcnow().isoformat()
    patient.outputs.run_duration_seconds = duration

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    model_path  = REPORTS_DIR / f"patient_model_{ts}.json"
    report_path = REPORTS_DIR / f"report_{ts}.md"

    try:
        model_path.write_text(patient.model_dump_json(indent=2))
        if combined:
            report_path.write_text(combined)
        (REPORTS_DIR / "latest_model.json").write_text(patient.model_dump_json(indent=2))
        if combined:
            (REPORTS_DIR / "latest_report.md").write_text(combined)
    except Exception as e:
        logger.warning("Could not persist reports: %s", e)

    _cb("Done", 100)

    return {
        "status":  "complete",
        "duration_seconds": duration,
        "agents_succeeded": {
            "ingestion": patient.outputs.ingestion_complete,
            "cds":       patient.outputs.cds_complete,
            "recovery":  patient.outputs.recovery_complete,
            "report":    patient.outputs.report_complete,
        },
        "patient":   patient,
        "cds":       cds,
        "recovery":  recovery,
        "rehab":     rehab,
        "cv":        cv,
        "report_md": combined,
        "report_md_ru": ru_report,
    }


def load_latest() -> Optional[dict]:
    for d in [_TMP_REPORTS, _APP_REPORTS]:
        mf = d / "latest_model.json"
        rf = d / "latest_report.md"
        if mf.exists():
            return {
                "model":  json.loads(mf.read_text()),
                "report": rf.read_text() if rf.exists() else "",
            }
    return None
