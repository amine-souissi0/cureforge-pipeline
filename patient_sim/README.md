# Patient Medical Agent — CureForge Patient Simulation

## Overview
4-agent LLM pipeline for clinical decision support (Oleg I.T., 83y, post-CEA stroke).

## Demo URL
https://amine-souissi0-cureforge-dashboard-streamlit-app-ypvvfl.streamlit.app

## Architecture
```
ING → CDS → RLP → RPT
```
- **ING** (Ingestion): Parses 8 clinical docs → structured JSON with provenance
- **CDS** (Clinical Decision Support): Anticoag/BP/rehab recommendations (EN+RU)
- **RLP** (Recovery & Longevity Planner): 3-phase roadmap, speech therapy, family guide (EN+RU)
- **RPT** (Report): Bilingual Markdown report — EN for investors, RU for doctors

## Setup
```bash
pip install streamlit pydantic requests pandas
export GROQ_API_KEY=your_key_here
streamlit run dashboard.py
```

## Key Files
- `models/patient.py` — Pydantic patient schema (Demographics, Neurology, Imaging, Comorbidities)
- `pipeline.py` — Orchestrator (run_analysis / load_latest)
- `agents/` — 4 LLM agents (base.py, ingestion, cds, recovery, report)
- `dashboard.py` — 6-tab Streamlit UI
- `data/` — Clinical documents (8 .txt files), DICOM metadata JSONs

## NIHSS Correction (02.06.26)
Trajectory: 15 → 18 → 14 → 12 (minimum confirmed as 12, not 7-9 as previously recorded)

## Corp Repo
This module was integrated from: https://github.com/amine-souissi0/cureforge-dashboard
