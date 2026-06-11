# External work report — validation against this repository

This document corrects an earlier technical review that described this codebase at a high level without fully matching the tree. Use it when sharing architecture decisions with stakeholders.

## Corrections to the prior assessment

| Prior claim | Verified state in this repository |
|-------------|-----------------------------------|
| No visible unit or integration tests | **`tests/`** includes `test_email_agent.py`, `test_intent_parser.py`, `test_personalization.py`, `test_webhook.py`, and **`test_roadmap_agents.py`** (roadmap agents with mocked HTTP/OpenAI). Run `pytest tests/ -v`. |
| No memory / no context across interactions | The **investor MVP** persists **`OutreachRecord`** in SQLite (`models/database.py`): send status, reply intent, timestamps, and raw reply excerpt. Grant and other roadmap agents historically did not keep conversational session state; **agent session/thread** storage is added as part of the evolution roadmap (`AgentSession` model). |
| Repository focused only on grant filling | The README lists **six roadmap agents** (grant, preprint, journal, patent, DUA, FDA) plus **email, personalization, intent parsing**, webhook, and Streamlit dashboard. Grant automation is one component. |

## What remains accurate

- Roadmap agents largely used **single-pass LLM** calls without built-in **generate / review / refine** loops (addressed for grants via **`draft_narrative_workflow`** in `agents/grant_agent.py`).
- **No central orchestrator** originally; a **`orchestrator/router.py`** task router is introduced for dispatch and extension.
- **SF424 / portal submission** for grants and similar human-in-the-loop steps remain outside full automation, as documented in the README.

## Evolution summary (implemented direction)

1. **Modular boundaries** — `core/llm.py`, `core/http.py` for shared LLM and HTTP access (piloted from the grant agent).
2. **Grant workflows** — validation of `project_info`, optional multi-step narrative drafting, structured package output under `output/grants/`.
3. **Orchestration and session memory** — `orchestrator/router.py` plus `AgentSession` for JSON payloads keyed by `session_id` / `task_type`.
4. **Production-oriented webhook** — optional **`WEBHOOK_API_KEY`**, structured JSON logging via **`core/logging_config.py`**, **`POST /tasks`** enqueue with **`GET /tasks/{id}`** status (in-process async; replace with Redis/RQ for horizontal scale).

For the original phased narrative (refactor → workflows → orchestration → production), see the repository plan agreed with the engineering team; this file only validates facts and points to where behavior lives in code.
