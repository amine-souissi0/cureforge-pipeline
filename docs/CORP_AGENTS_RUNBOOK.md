# CureForge Corp Agents — Runbook (ClickUp 86exvcaq5)

Four multi-agent systems live in this repository. Use this guide to run and verify each one.

## Repository layout

| Agent | Path | Corp GitHub | Purpose |
|-------|------|-------------|---------|
| **1. Outreach / Communication** | `packages/outreach-agent/` | This repo | Investor outreach (Resend email, webhook intent, Streamlit dashboard) |
| **2. Ukhvat news decomposition** | `packages/ukhvat-news-agent/` | This repo | @UkhvatNews → LLM parse → ClickUp tasks (+ bridge to outreach) |
| **3. Recruiting pipeline + CEO gate** | `app/` (repo root) | This repo `main` | Gmail intake → evaluate → founder/CEO review gate → offer |
| **4. Patient medical AI (father's case)** | `packages/patient-sim-agent/` | This repo | 7-agent pipeline, EN/RU report, camera + speech protocols (ClickUp 86exv176h) |

---

## Agent 1 — Outreach (Communication Agent)

**What it does:** Personalizes and sends investor emails, classifies replies via webhook, shows status on Streamlit dashboard.

```bash
cd packages/outreach-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill RESEND_API_KEY, etc.

# Tests (no API keys required — mocked)
pytest tests/ -v

# Dashboard
streamlit run dashboard/app.py

# Webhook server
uvicorn webhook.server:app --host 0.0.0.0 --port 8000

# Send outreach (dry run)
python -m scripts.run_outreach --csv data/investors_sample.csv --dry-run
```

**Bridge from news agent:** `packages/ukhvat-news-agent` queues drafted letters via `scripts.queue_drafted_outreach`.

---

## Agent 2 — Ukhvat news → ClickUp (Arshie / Archie pipeline)

**What it does:** Monitors longevity news forwarded to the Telegram bot, decomposes articles with Groq/LLaMA, creates ClickUp tasks (Developers / Sales / Other).

```bash
cd packages/ukhvat-news-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # GROQ, TELEGRAM, CLICKUP list IDs

# Verify connections (Groq + ClickUp + Telegram bot)
python orchestrator.py --test

# One-shot run (process new posts once)
python orchestrator.py --once

# Daemon (poll every POLL_INTERVAL seconds)
python orchestrator.py
```

**ClickUp lists:** Configure `CLICKUP_LIST_DEVELOPERS`, `CLICKUP_LIST_SALES`, `CLICKUP_LIST_OTHER` in `.env` for the decomposition workspace Oleg tagged.

**Optional:** Set `COMMUNICATION_AGENT_PATH` to `../outreach-agent` so investor letters queue into the outreach DB.

---

## Agent 3 — Recruiting pipeline + CEO gate (Sairam / corp main)

**What it does:** Engineering recruiting via email (`cureforge.pipeline@gmail.com`). Candidates submit tasks; evaluation FSM runs; **CEO/founder gate** approves before offers.

```bash
# From repo root
pip install -r requirements.txt
cp .env.example .env   # GROQ/ANTHROPIC, Gmail OAuth, JWT_SECRET_KEY, ADMIN_EMAIL

# Tests
pytest tests/ -v

# Local stack
docker compose up -d
uvicorn app.main:app --reload --port 8000
```

**Dev CEO gate UI:** `/ui` after login at `/auth/login`

| Setting | Dev value (from product brief) |
|---------|-------------------------------|
| Login | `admin@cureforge.com` / `admin123` (set `ADMIN_EMAIL` + `ADMIN_PASSWORD` in `.env`) |
| Pipeline inbox | `cureforge.pipeline@gmail.com` — send email to trigger candidate flow |

**Note:** LinkedIn is **not** automated in code; recruitment is **email + CEO gate**. Sairam submission zip matched `main` (already merged).

---

## Agent 4 — Patient medical AI (7 agents, father's case)

**What it does:** Post-CEA stroke recovery — bilingual EN/RU clinical report, Agents 5–7 (rehab, CV tracker, speech sim), camera + speech protocols.

```bash
cd packages/patient-sim-agent
pip install -r ../outreach-agent/requirements.txt   # shared deps
streamlit run streamlit_app.py
```

**Protocols (WHERE / WHEN / WHAT):**
- Camera: `guides/camera_recording_protocol.md` — 08:00 / 13:00 / 18:00, exercises A1→L3
- Speech: `guides/speech_recording_protocol.md` — RU 09:30 / EN 15:00 / SW 19:30

**ClickUp deliverable:** task [86exv176h](https://app.clickup.com/t/86exv176h) — full report posted in task comments.

---

## Verification checklist (for ops / Oleg)

- [ ] `packages/outreach-agent`: `pytest tests/ -q` passes
- [ ] `packages/ukhvat-news-agent`: `python orchestrator.py --test` shows Groq + ClickUp + Telegram OK
- [ ] Root recruiting pipeline: `pytest tests/ -q` passes
- [ ] Outreach dashboard loads (`streamlit run packages/outreach-agent/dashboard/app.py`)
- [ ] CEO gate UI loads at `/ui` on deployed recruiting instance
- [ ] `packages/patient-sim-agent`: `streamlit run streamlit_app.py` loads; guides present under `guides/`

---

## Deployment

| Agent | Suggested host |
|-------|----------------|
| Outreach | Streamlit Cloud / Railway + webhook URL for Resend |
| Ukhvat news | Always-on VM or Railway worker (`python orchestrator.py`) |
| Recruiting | Railway (`railway.toml` at repo root) |

---

*Task: [86exvcaq5](https://app.clickup.com/t/86exvcaq5) — Upload to corp resources & launch 3 multi agents*
