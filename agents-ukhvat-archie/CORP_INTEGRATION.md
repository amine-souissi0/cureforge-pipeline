# Ukhvat News Decomposition Agent (Archie) — Corp Integration

## What it does
Monitors the **Ukhvat News** Telegram channel (https://t.me/UkhvatNews),
parses each longevity-science article with an LLM, and auto-creates
structured **ClickUp tasks** for the Dev and Sales teams.

## Pipeline
```
Telegram (UkhvatNews) → ArticleParser → {DevTaskAgent, SalesInvestorAgent} → ClickUp
```

## Agents
- `agents/telegram_monitor.py` — polls UkhvatNews channel
- `agents/article_parser.py` — LLM decomposition of each post
- `agents/dev_task_agent.py` — creates developer tasks
- `agents/sales_investor_agent.py` — creates sales/investor tasks
- `integrations/clickup_client.py` — ClickUp task creation
- `orchestrator.py` — daemon (polls every POLL_INTERVAL) or `--once`

## Corp ClickUp targets (Cure Forge AI workspace 90182612756)
- Space: Team Space `901810593272`
- Dev list: `901817334379`
- Team list: `901817334380`
- Features list: `901818295785`

## Required environment (.env)
```
GROQ_API_KEY=          # or NVIDIA_API_KEY (NVIDIA NIM)
TELEGRAM_BOT_TOKEN=
TELEGRAM_USER_ID=
TELEGRAM_CHANNEL=UkhvatNews
CLICKUP_API_TOKEN=
CLICKUP_WORKSPACE_ID=90182612756
CLICKUP_SPACE_ID=901810593272
CLICKUP_LIST_DEVELOPERS=901817334379
CLICKUP_LIST_SALES=901817334380
CLICKUP_LIST_OTHER=901818295785
```

## Run
```bash
pip install -r requirements.txt
python orchestrator.py --test   # verify connections
python orchestrator.py --once   # process latest posts once
python orchestrator.py          # daemon mode
```

## Task assignment policy (per CEO request)
Decomposed tasks should be assigned with:
- **When**: scheduled by urgency tier (URGENT → this sprint, PLANNED → next sprint)
- **Who**: Dev tasks → developer list; Sales/investor → sales list
- **Priority**: must NOT override existing sprint priorities — appended as backlog
  unless flagged URGENT by the parser.

## Status
- ClickUp connection: ✅ verified (token valid, lists reachable)
- LLM: requires valid GROQ_API_KEY or NVIDIA_API_KEY
- Telegram: requires bot token + the bot added to UkhvatNews

Original repo: https://github.com/arshiefatima/longevity-multi-agent
