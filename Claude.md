# CureForge Pipeline Agent — Claude Code Quick-Start Guide

## What You Have

Two files have been generated to start your project:

1. **Claude.md** — Complete guide to integrating Claude API into your pipeline
2. **cureforge_substrate_init.py** — Substrate foundation (FSM, data models, schemas)

## Project Status

You're starting at **Milestone 1: Substrate** — complete. The following are ready:

- ✅ FSM engine with canonical transition table
- ✅ Pydantic data models (candidates, messages, tasks, evaluations, audit log)
- ✅ Schema validators for all Claude agent outputs
- ✅ Alembic migration template
- ✅ Unit tests (FSM, schema validation, data models)

## How to Use Claude Code to Continue

### Step 1: Initialize the Project

```bash
python cureforge_substrate_init.py
```

This will:
- Run unit tests to verify FSM and schema validators work
- Print the FSM transition table
- Output Alembic migration template

Expected output:
```
CureForge Pipeline Agent — Milestone 1: Substrate Initialization
=================================================================
[1] Testing FSM Engine...
✓ FSM transition tests passed

[2] Testing Schema Validators...
✓ Schema validation tests passed

[3] Testing Data Models...
✓ Candidate model tests passed

[4] FSM Transition Table:
  NEW                   → ENGAGED                 (predicate: intake_complete)
  ENGAGED               → TASK_ASSIGNED           (predicate: intent_interested_and_task_generated)
  ...
```

### Step 2: Use Claude Code for M2 (Channel I/O)

**Milestone 2: Channel I/O** — Gmail integration + reply classification

In Claude Code (or Claude.ai with extended context), ask:

```
I have a CureForge pipeline agent project with FSM and data models.
Now I need to build Milestone 2: Channel I/O.

Implement:
1. FastAPI service with Gmail OAuth2 integration (using Google Cloud credentials)
2. Async Gmail message polling / push notification handler
3. Route classified emails to Reply Classifier agent
4. Schema validation with human routing on failure
5. Celery task integration for async email processing

Use the existing substrate from cureforge_substrate_init.py.
Assume Claude API key is in AWS Secrets Manager.
Generate:
- app/services/gmail_service.py (OAuth, polling, webhook)
- app/agents/reply_classifier.py (LLM agent with Claude API)
- app/api/candidates.py (REST endpoints)
- requirements.txt
- Integration test file
```

### Step 3: Use Claude Code for M3 (Templating)

**Milestone 3: Templating** — Template library + Template Responder agent

Ask Claude:

```
Build Milestone 3: Templating for CureForge pipeline.

Implement:
1. Template library with candidate-facing templates:
   - acknowledgment
   - answer-common-question
   - task-assignment-cover
   - feedback-delivery
   - warm-hold
   - offer-cover
2. Template Responder agent (Claude Haiku for template population)
3. Send policy engine (auto-send vs. draft-for-approval)
4. Founder approval queue endpoint
5. Email send via Gmail API

Templates must:
- Never include deadlines
- Never expose rubric structure
- Support dynamic field injection (candidate name, task brief, scores, etc.)
- Be founder-customizable

Generate:
- app/templates/__init__.py (template registry)
- app/agents/template_responder.py
- app/services/send_policy.py
- tests/test_templates.py
```

### Step 4: Continue Through Milestones

Each milestone builds on the previous. Follow this sequence:

| M | Milestone | Focus | Core Deliverables |
|---|-----------|-------|-------------------|
| 1 | ✅ Substrate | FSM, models, schemas | cureforge_substrate_init.py |
| 2 | Channel I/O | Gmail, classification | Gmail service, reply classifier, API |
| 3 | Templating | Template system, responder | Template library, template responder |
| 4 | Decomposition | Task generation, GitHub | Task decomposer, repo provisioning |
| 5 | Evaluation | Sandbox, probes, scoring | Sandbox runner, evaluation agent |
| 6 | Loop & Gate | Feedback, decision gate | Feedback controller, decision engine |
| 7 | Surfaces | Dashboard, offer drafter | Evaluation table, offer drafter, UI |
| 8 | Hardening | Security review, dry-run | Isolation review, full E2E test |

## Claude Code Workflow

For each milestone, use this prompt pattern:

```
CureForge Pipeline Agent — [Milestone N]: [Name]

Project context:
- Type: Recruiting pipeline automation (finite state machine)
- Tech stack: Python async, FastAPI, PostgreSQL, Redis, Docker
- AI layer: Claude API (Haiku for speed, Opus for reasoning)
- Model pins: See config/models.py
- All AI outputs: schema-validated, never bypass FSM
- All candidate code: sandboxed, untrusted
- All outputs: audit-logged

Existing code:
- FSM engine with transition table
- Pydantic models (candidates, messages, tasks, evaluations, audit_log)
- Schema validators (classifier, decomposer, evaluator, offer_drafter)

Implement [specific components for this milestone]:
1. [Component A]
2. [Component B]
3. [Component C]

Requirements:
- Production-grade: no shortcuts for MVP
- Type hints everywhere (mypy strict)
- Async/await throughout
- No global state
- Schema validation mandatory
- Audit logging on every state change
- Error handling with human routing

Provide:
- Source files (Python modules)
- Pydantic schemas (if new agents)
- Unit tests (>80% coverage)
- Integration test
- Example usage
```

## Key Guidelines for Claude Code Prompts

### 1. Always Specify Constraints

```
Security constraints:
- Candidate code never runs on production host
- Secrets always in secret manager, never in code
- No hardcoded API keys or credentials
- Audit log is append-only

Compliance constraints:
- No rubric exposure to candidates
- No proprietary IP in task briefs
- No deadlines in candidate-facing messages
- GDPR-compliant data handling (PII retention policy)
```

### 2. Be Explicit About AI Integration

```
Claude API integration:
- Model: claude-3-5-haiku-20241022 (for this agent)
- Max tokens: 500
- Temperature: 0.0
- Output schema: ReplyClassifierOutput (Pydantic)
- Validation: Mandatory before use
- Retry on schema failure: 1 retry, then human routing
- Cost tracking: Log tokens in/out to audit_log
```

### 3. Reference the Build Brief

```
See CureForge_Recruiting_Pipeline_Agent_Build_Brief__1_.pdf section [N]
for the official specification.

From the brief:
- Hard constraint §3.2: Candidate code must be sandboxed
- Component spec §5.3: Template Responder must not expose rubric
- Probe methodology §8.3: Evaluation is evidence-based, not code-reading
```

### 4. Ask for Tests First

```
Before implementation, generate:
1. Unit test cases (mock external dependencies)
2. Integration test (with mock Claude API)
3. E2E test (with real Claude API call to staging)
4. Security test (sandbox escape, injection, etc.)

Then: Implementation that passes all tests.
```

## File Organization

Expected structure after all milestones:

```
cureforge/
├── app/
│   ├── __init__.py
│   ├── main.py (FastAPI app entry)
│   ├── config.py (models, rubric, thresholds)
│   ├── schemas.py (Pydantic models)
│   ├── fsm.py (FSM engine)
│   ├── database.py (SQLAlchemy setup)
│   ├── agents/
│   │   ├── reply_classifier.py
│   │   ├── template_responder.py
│   │   ├── task_decomposer.py
│   │   ├── evaluation_agent.py
│   │   └── offer_drafter.py
│   ├── services/
│   │   ├── gmail_service.py
│   │   ├── github_service.py
│   │   ├── sandbox_runner.py
│   │   ├── claude_client.py
│   │   └── send_policy.py
│   ├── api/
│   │   ├── candidates.py
│   │   ├── evaluations.py
│   │   ├── webhooks.py
│   │   └── audit.py
│   └── models.py (SQLAlchemy ORM)
├── frontend/
│   ├── app/
│   ├── components/
│   └── pages/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── migrations/ (Alembic)
├── prompts/ (versioned Claude prompts)
│   ├── classifier.md
│   ├── decomposer.md
│   ├── evaluator.md
│   └── offer_drafter.md
├── docker/
│   ├── Dockerfile.app
│   ├── Dockerfile.worker
│   ├── Dockerfile.sandbox
│   └── docker-compose.yml
├── config/
│   ├── models.py (Claude models, pins, settings)
│   └── corpus.yaml (injected at deploy time)
├── requirements.txt
├── pyproject.toml
├── .env.example
└── README.md
```

## Running the Project

After M2+ is built:

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export CLAUDE_API_KEY="sk-..."
export DATABASE_URL="postgresql://user:pass@localhost/cureforge"
export GMAIL_OAUTH_SECRET="..."
export GITHUB_OAUTH_SECRET="..."

# Run database migrations
alembic upgrade head

# Start the app
uvicorn app.main:app --reload

# In another terminal: start Celery workers
celery -A app.celery_app worker -l info

# View dashboard
open http://localhost:3000
```

## Testing Strategy

Before marking a milestone complete:

```bash
# Unit tests
pytest tests/unit/ -v --cov=app --cov-report=html

# Integration tests (with mocked Claude API)
pytest tests/integration/ -v

# E2E test (with real Claude API to staging)
pytest tests/e2e/ -v

# Type checking
mypy app/ --strict

# Linting
ruff check app/

# Security scan
bandit -r app/
```

## Prompt Best Practices for Claude Code

### ✅ Good: Specific, Constrained, Testable

```
Build the Reply Classifier agent.

Spec (from Build Brief §5.2):
- Fast model (Claude Haiku)
- Input: email body + candidate context
- Output: ReplyClassifierOutput schema
- Confidence < 0.75 or intent == OTHER → route to founder
- Validate schema before use
- Log every call to audit_log

Provide:
- app/agents/reply_classifier.py
- Test: 5 test cases (high confidence, low confidence, invalid JSON, ambiguous)
- Integration test with mock Gmail
```

### ❌ Bad: Vague, Open-Ended

```
Build the classifier.

Provide code that integrates with Claude.
```

### ✅ Good: Referencing Constraints

```
Task Decomposer agent.

CRITICAL constraints (non-negotiable):
- §3.3: No proprietary IP in output
- §3.4: Frontier blocklist enforcement (fail-closed)
- §3.5: No rubric structure in candidate-facing output
- §7: Corpus is config-injected, not hardcoded

Verify in tests:
1. Blocklist rejection on frontier task
2. Abstraction rules (strip internal nomenclature)
3. Zero rubric language in candidate_brief
```

### ❌ Bad: Ignoring Constraints

```
Generate task decomposition logic.
```

## Next Steps

1. **Read the full Build Brief**: CureForge_Recruiting_Pipeline_Agent_Build_Brief__1_.pdf
2. **Read the Architecture Blueprint**: CureForge_AI_Architecture_Blueprint.docx
3. **Read the Claude Integration Guide**: Claude.md (in this package)
4. **Run the substrate**: `python cureforge_substrate_init.py`
5. **Open Claude Code** and ask for M2 using the pattern above
6. **Work through milestones sequentially** — don't skip to M5 before M2 is done
7. **Test after each milestone** before moving to the next
8. **Dry-run after M8** with synthetic candidates and placeholder corpus

## Support

If you hit issues with Claude Code generation:

1. **Schema mismatch**: Paste the exact Pydantic schema you're using in the prompt
2. **Integration gaps**: Ask Claude to generate a "glue layer" integrating the new code with existing FSM/services
3. **Audit logging**: Ask Claude to add `await audit_log.append(...)` calls to every major function
4. **Type hints**: Ask for strict mypy compliance in follow-up prompts

## Final Note

This is a production system, not a prototype. Every component Claude Code generates should be:
- Type-safe (mypy strict)
- Fully tested (unit + integration)
- Audit-logged (every action)
- Schema-validated (before use)
- Security-conscious (secrets in managers, untrusted input sandboxed)

Use Claude Code to accelerate, but treat the Build Brief and Architecture Blueprint as law. No shortcuts.
