# CureForge Pipeline Agent

AI-powered engineering recruiting pipeline. Automates candidate intake through offer drafting using Claude API, with a finite state machine governing every transition.

> **Corp multi-agent stack (ClickUp 86exvcaq5):** This repo also contains the **outreach** and **Ukhvat news decomposition** agents under `packages/`, plus this root app (recruiting + CEO gate). See **[docs/CORP_AGENTS_RUNBOOK.md](docs/CORP_AGENTS_RUNBOOK.md)** for how to run all three.

## Architecture

```
Inbound Email (Gmail)
        │
        ▼
Reply Classifier (Haiku)
        │
        ├── TASK_SUBMISSION ──► Sandbox Runner ──► Evaluation Agent (Opus)
        │                                                    │
        ├── INTERESTED / QUESTION ──► Template Responder     ▼
        │                            (Haiku)         Decision Engine
        └── DECLINE ──► FSM: WITHDRAWN                      │
                                             ┌──────────────┼──────────────┐
                                             ▼              ▼              ▼
                                      HIRE_RECOMMENDED  RESUBMIT     WARM_HOLD
                                             │
                                             ▼
                                      Offer Drafter (Sonnet)
                                             │
                                             ▼
                                      ApprovalQueue ──► Founder Review
```

## Milestones

| # | Milestone | Description |
|---|-----------|-------------|
| M1 | Substrate | FSM, Pydantic schemas, audit log |
| M2 | Channel I/O | Gmail OAuth2, Pub/Sub webhook, reply classifier |
| M3 | Templating | 6 email templates, approval queue, send policy |
| M4 | Decomposition | Task decomposer, corpus, blocklist, GitHub provisioning |
| M5 | Evaluation | Evaluation agent, weighted rubric, sandbox runner |
| M6 | Loop & Gate | Decision engine, feedback controller, gate API |
| M7 | Surfaces | Dashboard API, offer drafter, candidate store |
| M8 | Hardening | Sandbox pre-scan, rate limiter, readiness probe, E2E tests |

## Agents

| Agent | Model | Role |
|-------|-------|------|
| Reply Classifier | Claude Haiku 3.5 | Classifies inbound candidate emails |
| Template Responder | Claude Haiku 3.5 | Populates email templates |
| Task Decomposer | Claude Sonnet 3.5 | Generates sandboxed engineering problems |
| Evaluation Agent | Claude Opus 4.7 | Scores submissions against rubric |
| Offer Drafter | Claude Sonnet 3.5 | Drafts offer letters |

## FSM States

```
NEW → ENGAGED → TASK_ASSIGNED → AWAITING_SUBMISSION → UNDER_EVALUATION
                                                               │
                                                        FEEDBACK_SENT
                                                        ┌──────┼──────┐
                                                        ▼      ▼      ▼
                                                   RESUBMIT  HIRE   WARM
                                                             RECOMMENDED HOLD
                                                               │
                                                        OFFER_DRAFTED → HIRED
                                                   WITHDRAWN (any stage)
```

## Setup

**Requirements:** Python 3.11+, Redis (for Celery)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Environment variables:**

```bash
export ANTHROPIC_API_KEY=your_key_here
export GOOGLE_CREDENTIALS_FILE=config/google_credentials.json
export REDIS_URL=redis://localhost:6379/0
export GITHUB_TOKEN=your_github_token        # for sandbox repo provisioning
export GITHUB_ORG=your-github-org
```

**Run the API:**

```bash
uvicorn app.main:app --reload
```

**Run tests:**

```bash
pytest tests/
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/candidates/intake` | Add a new candidate |
| POST | `/candidates/webhook` | Gmail Pub/Sub push handler |
| GET | `/gate/{id}/status` | Current gate status for a candidate |
| POST | `/gate/{id}/decide` | Run feedback loop + FSM transition |
| POST | `/gate/{id}/override` | Founder force-override FSM state |
| POST | `/gate/{id}/resubmit` | Accept and evaluate a resubmission |
| GET | `/dashboard/pipeline` | Full pipeline overview |
| GET | `/dashboard/candidate/{id}` | Per-candidate detail |
| GET | `/dashboard/drafts` | Pending approval queue |
| POST | `/dashboard/offer/{id}` | Draft an offer letter |
| GET | `/health/readiness` | Readiness probe |
| GET | `/health/costs` | Per-agent Claude API spend |
| GET | `/health/checklist` | Pre-production checklist |

## Security

- All Claude outputs are schema-validated before use; failures route to human review
- Candidate submissions are pre-scanned for dangerous patterns (network, subprocess, dynamic imports) before sandbox execution
- `internal_spec`, `red_flags`, and `dimension_scores` are never returned in candidate-facing API responses
- Emails requiring founder review are queued as drafts — only acknowledgments are auto-sent
- Rate limiter: 600 req/min per IP (sliding window, in-memory)
- API key loaded from environment; never logged or embedded in code

## Tests

```
tests/
├── e2e/              # 4 full synthetic candidate journeys
├── integration/      # Gmail webhook, intake, classification
└── unit/             # Per-milestone unit tests (M1–M8)
```

```
184 tests, 0 failures
```
