# CureForge Pipeline Agent — Complete Claude Code + Antigravity Workflow Guide

## Executive Summary

You have three files ready:
1. **Claude.md** — Claude API integration specification
2. **cureforge_substrate_init.py** — Runnable substrate foundation
3. **CLAUDE_CODE_QUICK_START.md** — Milestone prompts for Claude Code

**Next steps:**
1. Run substrate locally (verify foundation)
2. Use **Claude Code** (not Antigravity) to generate each milestone
3. Integrate outputs into project
4. Test, commit, move to next milestone

---

## Part 1: Understanding Your Tools

### Claude Code vs. Antigravity

| Tool | Use Case | When to Use |
|------|----------|------------|
| **Claude Code** (CLI) | Generate code for specific components | Milestones M2–M8 ✅ |
| **Antigravity** | Generate project scaffold, boilerplate | Initial setup only |
| **Claude.ai** (Web) | Copy-paste prompts, interactive coding | Alternative to Claude Code CLI |

**Decision: Use Claude Code for this project.** Antigravity is for creating blank project scaffolds; you already have your substrate, so Claude Code is more efficient.

---

## Part 2: Pre-Flight Checklist (5 minutes)

### 2.1 Verify Your Environment
```bash
# Check Python version
python3 --version  # Should be 3.10+

# Check you're in project directory
pwd  # Should show: .../cureforge-pipeline

# List files
ls -la
# Should show:
# - Claude.md
# - cureforge_substrate_init.py
# - CLAUDE_CODE_QUICK_START.md
# - venv/
```

### 2.2 Activate Virtual Environment
```bash
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows
```

Verify:
```bash
which python  # Should show: .../venv/bin/python
```

### 2.3 Set Environment Variables
```bash
# Create .env file
cat > .env << 'EOF'
ANTHROPIC_API_KEY="sk-..."  # Your actual key
EOF

# Load in current shell
export ANTHROPIC_API_KEY="sk-..."
```

Verify:
```bash
echo $ANTHROPIC_API_KEY  # Should print your key
```

### 2.4 Verify Claude API Access
```bash
python3 << 'EOF'
import anthropic
client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=100,
    messages=[{"role": "user", "content": "Say 'Ready to build'."}]
)
print(response.content[0].text)
EOF
```

**Expected output:** `Ready to build.`

If you see an API error, check your ANTHROPIC_API_KEY.

---

## Part 3: Step-by-Step Workflow

### STEP 1: Run Substrate (10 minutes)

**Purpose:** Verify FSM, models, schemas all work before generating code.

```bash
python cureforge_substrate_init.py
```

**Expected output:**
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
  ENGAGED               → WITHDRAWN                (predicate: intent_declined)
  ...

✓ Substrate initialization complete!

Next steps:
  1. Create virtual environment: python -m venv venv
  2. Install dependencies: pip install fastapi uvicorn sqlalchemy pydantic
  3. Initialize Alembic: alembic init alembic
  4. Add migration: alembic revision --autogenerate -m 'init schema'
  5. Apply migration: alembic upgrade head
  6. Start M2: Channel I/O (Gmail integration)
=================================================================
```

✅ **If you see ✓ all tests pass: PROCEED. If any test fails: DEBUG BEFORE CONTINUING.**

---

### STEP 2: Create Project Structure (5 minutes)

```bash
# Create directories
mkdir -p app/{agents,services,api,models}
mkdir -p tests/{unit,integration,e2e}
mkdir -p config
mkdir -p prompts
mkdir -p migrations
mkdir -p docker

# Create __init__.py files
touch app/__init__.py
touch app/models.py
touch app/main.py
touch app/database.py
touch app/fsm.py
touch app/config.py
touch app/celery.py
touch config/__init__.py
touch config/models.py
touch config/templates.py
touch config/corpus.yaml
touch config/rubric.yaml
touch tests/__init__.py

# Create config files
touch .env.example
touch requirements.txt
touch pyproject.toml
touch .gitignore
touch Dockerfile
touch docker-compose.yml
```

**Result:**
```
cureforge-pipeline/
├── Claude.md
├── cureforge_substrate_init.py
├── CLAUDE_CODE_QUICK_START.md
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   ├── database.py
│   ├── fsm.py
│   ├── config.py
│   ├── celery.py
│   ├── agents/
│   ├── services/
│   ├── api/
│   └── models/
├── tests/
│   ├── __init__.py
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── config/
│   ├── __init__.py
│   ├── models.py
│   ├── templates.py
│   ├── corpus.yaml
│   └── rubric.yaml
├── prompts/
├── migrations/
├── docker/
├── .env.example
├── requirements.txt
├── pyproject.toml
├── .gitignore
├── Dockerfile
└── docker-compose.yml
```

---

### STEP 3: Copy Substrate to Project (5 minutes)

Extract the FSM, schemas, and models from `cureforge_substrate_init.py` and copy into `app/fsm.py` and `app/models.py`.

```bash
# Create app/fsm.py
cat > app/fsm.py << 'EOF'
# Copy FSMEngine class and CandidateState enum from cureforge_substrate_init.py
EOF

# Create app/schemas.py
cat > app/schemas.py << 'EOF'
# Copy all Pydantic schema classes (ReplyClassifierOutput, etc.) from cureforge_substrate_init.py
EOF
```

Or manually copy-paste the relevant classes.

---

### STEP 4: Initialize Git (5 minutes)

```bash
git init
git config user.name "Your Name"
git config user.email "you@example.com"

# Create .gitignore
cat > .gitignore << 'EOF'
venv/
__pycache__/
*.pyc
.env
.env.local
.vscode/
.idea/
*.db
*.sqlite
.pytest_cache/
htmlcov/
dist/
build/
*.egg-info/
node_modules/
.DS_Store
EOF

# Initial commit
git add .
git commit -m "M0: Project scaffold + substrate foundation"
```

---

### STEP 5: Use Claude Code for M2 (Milestone 2: Channel I/O)

**Time: 2–4 hours**

#### 5.1 Open Claude Code or Claude.ai

**Option A: Claude Code CLI**
```bash
# If installed as command-line tool
claude code
```

**Option B: Claude.ai Web**
- Go to https://claude.ai
- Create new conversation
- Paste prompt below

#### 5.2 Use the M2 Prompt from CLAUDE_CODE_QUICK_START.md

**Copy this entire prompt and paste into Claude:**

```
You are building the CureForge Recruiting Pipeline Agent.

PROJECT CONTEXT:
- Type: Recruiting pipeline automation
- Tech: Python async, FastAPI, PostgreSQL, Redis, Claude API
- Operating channels: Gmail (email), GitHub (code submission)
- AI layer: Claude API (Haiku for speed, Opus for reasoning)
- Governance: Explicit FSM with audit logging

SUBSTRATE (M1) — Already Complete:
- FSM engine with transition table (app/fsm.py)
- Pydantic data models: candidates, messages, tasks, evaluations, audit_log (app/models.py)
- Schema validators: ReplyClassifierOutput, TaskDecomposerOutput, EvaluationAgentOutput (app/schemas.py)

MILESTONE 2 SPECIFICATION (from Build Brief §5.2, §5.3):
Build Channel I/O — Gmail OAuth2 integration, Reply Classifier agent, email send policy.

REQUIREMENTS:

1. Gmail OAuth2 Service (app/services/gmail_service.py)
   - OAuth2 flow with PKCE (no stored passwords)
   - Async polling OR Google Pub/Sub push notifications
   - Send emails via Gmail API
   - Message ID tracking for idempotency
   - Error handling: rate limits, auth failures, network errors
   - Retry logic with exponential backoff

2. Reply Classifier Agent (app/agents/reply_classifier.py)
   - Model: claude-3-5-haiku-20241022
   - Input: email body + candidate context
   - Output: ReplyClassifierOutput schema (Pydantic)
   - Intent classification: INTERESTED | QUESTION | SCHEDULING | TASK_SUBMISSION | DECLINE | OTHER
   - Confidence threshold: 0.75 (below = route to founder)
   - Schema validation: retry once on failure, then route to founder
   - Audit logging: log every call with tokens in/out and cost

3. Send Policy Engine (app/services/send_policy.py)
   - Auto-send: acknowledgment, common-question templates
   - Draft-for-approval: task-assignment, feedback, warm-hold, offer templates
   - Founder approval queue for drafts
   - Status tracking: PENDING → APPROVED → SENT

4. FastAPI Endpoints (app/api/webhooks.py)
   - POST /webhooks/gmail — Gmail push notification ingestion
   - POST /webhooks/gmail/poll — Manual polling (fallback)
   - GET /candidates/{id}/messages — Message history
   - GET /approval-queue — Pending drafts
   - POST /approval-queue/{draft_id}/approve — Approve and send

5. Celery Tasks (app/celery_tasks.py)
   - classify_and_route(candidate_id, email_body) — async classification
   - send_email(candidate_id, template_id, context, auto_send=False) — async send
   - Background polling worker (optional)

6. Data Models Update (app/models.py)
   - Add MessageModel with direction, template_id, gmail_id
   - Add DraftModel for approval queue
   - Add AuditLogModel for immutable logging

HARD CONSTRAINTS (NON-NEGOTIABLE):
- §3.5: No rubric language in any outbound message
- §3.8: No deadlines in candidate-facing messages
- §3.9: Every action logged immutably with timestamp, actor, inputs, outputs
- Security: Secrets in AWS Secrets Manager, never in code
- Schema validation mandatory; invalid output routed to founder
- Audit logging: every Gmail send/receive, every classification

IMPLEMENTATION REQUIREMENTS:
- Strict type hints (mypy --strict compliant)
- Async/await throughout (no blocking calls)
- Pydantic schema validation before downstream use
- Celery task retry logic with exponential backoff
- Dead-letter queue for failed tasks
- Error messages logged, never suppressed
- Idempotency: Gmail message IDs tracked to prevent duplicates

PROVIDE:
1. app/services/gmail_service.py
2. app/agents/reply_classifier.py
3. app/services/send_policy.py
4. app/api/webhooks.py
5. app/celery_tasks.py (or app/workers/)
6. Updated app/models.py
7. tests/unit/test_classifier.py
8. tests/integration/test_gmail.py
9. .env.example (with Gmail config)
10. README_M2.md (setup instructions)

QUALITY BAR:
- Strict type hints (mypy --strict)
- >80% test coverage
- Error handling with human routing
- Full audit trail
- Production-ready (no prototype shortcuts)

SPECIFIC CLAUDE API INTEGRATION (from Claude.md):
- Model: "claude-3-5-haiku-20241022"
- Max tokens: 500
- Temperature: 0.0
- Retry: once on validation failure, then human routing
- Cost tracking: log tokens in/out per call
```

#### 5.3 Review Claude's Output

Claude will generate files. Review for:
- ✅ Strict type hints
- ✅ Schema validation
- ✅ Audit logging on every action
- ✅ No hardcoded secrets
- ✅ Error handling
- ✅ Tests included

#### 5.4 Integrate Output into Your Project

```bash
# Copy Claude-generated files into your project
# Example:
cp gmail_service.py app/services/
cp reply_classifier.py app/agents/
cp send_policy.py app/services/
cp webhooks.py app/api/
cp celery_tasks.py app/
cp test_classifier.py tests/unit/
cp test_gmail.py tests/integration/

# Update requirements.txt with new dependencies
# Claude will tell you what's needed:
# google-auth-oauthlib, google-auth-httplib2, fastapi, celery, redis, etc.
```

#### 5.5 Install Dependencies

```bash
pip install -r requirements.txt
```

#### 5.6 Run Tests

```bash
# Unit tests
pytest tests/unit/test_classifier.py -v

# Integration tests (with mocked Gmail)
pytest tests/integration/test_gmail.py -v

# Type checking
mypy app/ --strict

# Linting
ruff check app/
```

**Expected:** All tests pass, no type errors.

#### 5.7 Commit M2

```bash
git add app/ tests/ requirements.txt .env.example
git commit -m "M2: Channel I/O - Gmail OAuth, classifier, send policy"
```

---

### STEP 6: Repeat for M3–M8 (Same Pattern)

For each milestone (M3 Templating, M4 Decomposition, M5 Evaluation, M6 Loop & Gate, M7 Surfaces, M8 Hardening):

#### Template Workflow

1. **Copy prompt from CLAUDE_CODE_QUICK_START.md** (M3, M4, M5, M6, M7, M8 sections)
2. **Paste into Claude Code or Claude.ai**
3. **Add context:** "Existing code is in app/, tests/. Use same patterns as M2."
4. **Review output** for quality, tests, type hints
5. **Integrate** into project
6. **Run tests:** `pytest tests/ -v`
7. **Commit:** `git commit -m "M[N]: [Milestone Name]"`

#### Quick Reference: Milestone Timeframes

| M | Name | Claude Time | Integration | Tests | Total |
|---|------|-------------|-------------|-------|-------|
| 1 | ✅ Substrate | Done | Done | Done | Done |
| 2 | Channel I/O | 30 min | 30 min | 30 min | 2 h |
| 3 | Templating | 30 min | 30 min | 30 min | 2 h |
| 4 | Decomposition | 45 min | 30 min | 45 min | 2.5 h |
| 5 | Evaluation | 60 min | 45 min | 60 min | 2.5 h |
| 6 | Loop & Gate | 45 min | 30 min | 45 min | 2 h |
| 7 | Surfaces | 45 min | 45 min | 45 min | 2.5 h |
| 8 | Hardening | 60 min | 60 min | 60 min | 3 h |
| **TOTAL** | — | ~5.5 h | ~4 h | ~5.5 h | **~20–24 h** |

---

## Part 4: Best Practices for Claude Code Efficiency

### 4.1 Prompt Structure (Always Follow This)

```
[PROJECT CONTEXT]
- Type, tech stack, governance model

[EXISTING CODE REFERENCE]
- What's already done (FSM, models, schemas)
- Link to existing files

[SPECIFICATION]
- What to build (from Build Brief)
- Input/output contracts
- Constraints and hard requirements

[HARD CONSTRAINTS]
- Non-negotiable rules (security, compliance, audit)
- Reference §N from Build Brief

[QUALITY BAR]
- Type hints, tests, documentation standards

[DELIVERABLES]
- List of files to generate
```

**Don't use vague prompts.** Claude is most efficient with structured, specific inputs.

### 4.2 Review Before Accepting

After Claude generates code:

**Checklist:**
- ✅ Strict type hints (no `Any`, proper imports)
- ✅ Schema validation on all Claude API outputs
- ✅ Audit logging on state changes and API calls
- ✅ Error handling with human routing (not suppressed)
- ✅ Tests: unit + integration
- ✅ No hardcoded secrets
- ✅ No blocking I/O (async/await throughout)
- ✅ Follows project structure

**If Claude misses something:** Ask Claude to fix it. Example:
```
The code above is good but missing audit logging on every email send.
Add to send_email():
  await audit_log.insert({
    "event_type": "email_sent",
    "actor": "template_responder",
    "candidate_id": candidate_id,
    "template_id": template_id,
    "ts": datetime.utcnow()
  })
```

### 4.3 Integration Checklist

After copying Claude's files into your project:

```bash
# 1. Type checking
mypy app/ --strict
# Should pass with no errors

# 2. Linting
ruff check app/
# Should pass with no warnings

# 3. Unit tests
pytest tests/unit/ -v
# All tests should pass

# 4. Integration tests
pytest tests/integration/ -v
# All tests should pass

# 5. Imports
python -c "import app; print('Imports OK')"

# 6. Commit
git add app/ tests/ requirements.txt
git commit -m "M[N]: [Milestone Name]"
```

---

## Part 5: Common Issues & Solutions

### Issue 1: Import Errors After Integrating Claude Code

**Symptom:**
```
ModuleNotFoundError: No module named 'app.services.gmail_service'
```

**Solution:**
```bash
# Make sure __init__.py exists in all directories
touch app/services/__init__.py
touch app/agents/__init__.py
touch app/api/__init__.py

# Reinstall package in development mode
pip install -e .
```

### Issue 2: Type Errors (mypy --strict fails)

**Symptom:**
```
error: Argument 1 to "function" has incompatible type "Dict[str, Any]" instead of "CandidateModel"
```

**Solution:**
Ask Claude to fix:
```
mypy reports this error: [error message]

Fix by adding explicit type hints. Example:
  def process_candidate(candidate: CandidateModel) -> None:
```

### Issue 3: Tests Fail

**Symptom:**
```
FAILED tests/unit/test_classifier.py::test_high_confidence
AssertionError: expected confidence 0.95, got None
```

**Solution:**
1. Check the test
2. Ask Claude: "Fix test_high_confidence in tests/unit/test_classifier.py"

### Issue 4: Missing Dependencies

**Symptom:**
```
ModuleNotFoundError: No module named 'google.auth'
```

**Solution:**
```bash
pip install google-auth-oauthlib google-auth-httplib2
pip freeze > requirements.txt
```

### Issue 5: Audit Logging Missing

**Symptom:**
Code doesn't log state transitions or API calls.

**Solution:**
Ask Claude to add:
```
Add immutable audit logging to [function]. Before any state change or API call, log:
  await db.audit_log.insert({
    "timestamp": datetime.utcnow().isoformat(),
    "event_type": "...",
    "actor": "...",
    "candidate_id": "...",
    "inputs": {...},
    "outputs": {...}
  })
```

---

## Part 6: Antigravity Usage (Optional)

### When to Use Antigravity

Antigravity is useful for **initial project scaffolding**. Since you already have substrate, use it only for:
- Generating boilerplate (requirements.txt, Dockerfile, docker-compose.yml)
- Creating frontend scaffold (Next.js app structure)

### How to Use Antigravity

```bash
# Install Antigravity (if not already)
pip install antigravity-anthropic

# Generate project structure
antigravity init cureforge-pipeline --template fastapi-postgres

# Generate Docker setup
antigravity generate docker --python 3.11 --postgres
```

**In your case:** You've already done this manually, so **skip Antigravity**. Claude Code is more efficient for the iterative build you're doing.

---

## Part 7: Complete Workflow at a Glance

```
DAY 1: Foundation
├─ Run cureforge_substrate_init.py ✓
├─ Create project structure ✓
├─ Initialize Git ✓
└─ Verify Claude API access ✓

DAY 2: M2 (Channel I/O)
├─ Open Claude Code
├─ Paste M2 prompt
├─ Integrate outputs
├─ pytest tests/ -v ✓
└─ git commit -m "M2: ..." ✓

DAY 3: M3 (Templating)
├─ Paste M3 prompt
├─ Integrate + test
└─ Commit ✓

DAY 4: M4 (Decomposition)
├─ Paste M4 prompt
├─ Integrate + test
└─ Commit ✓

DAY 5: M5 (Evaluation)
├─ Paste M5 prompt
├─ Integrate + test
└─ Commit ✓

DAY 6: M6 (Loop & Gate)
├─ Paste M6 prompt
├─ Integrate + test
└─ Commit ✓

DAY 7: M7 (Surfaces)
├─ Paste M7 prompt
├─ Integrate + test
└─ Commit ✓

DAY 8: M8 (Hardening)
├─ Paste M8 prompt
├─ Integrate + test
├─ Full E2E test
└─ Commit ✓

DAY 9: Final Review
├─ Dry-run with synthetic candidates
├─ Security review
├─ Production checklist
└─ Ready to deploy ✓
```

**Total: ~20–24 hours of Claude Code + manual work = Production-ready system in 1.5 weeks**

---

## Part 8: Reference: Key Files to Know

### Files YOU Provide

```
Claude.md
  → Read for API integration details
  → Reference when Claude generates agent code

cureforge_substrate_init.py
  → Run once at the start
  → Extract FSM, models, schemas for app/fsm.py, app/models.py

CLAUDE_CODE_QUICK_START.md
  → Copy prompts (M2–M8) into Claude Code
  → Follow the structure for each milestone
```

### Files Claude GENERATES

Per milestone:
```
app/services/[service].py
app/agents/[agent].py
app/api/[endpoint].py
tests/unit/test_[component].py
tests/integration/test_[component].py
.env.example (updated)
README_M[N].md (setup instructions)
```

### Files YOU CREATE/MAINTAIN

```
app/
  __init__.py (imports)
  main.py (FastAPI app)
  database.py (SQLAlchemy session)
  fsm.py (from substrate)
  models.py (from substrate + updates)
  config.py (local config)

config/
  models.py (Claude model pins)
  templates.py (template library)
  corpus.yaml (task patterns)
  rubric.yaml (evaluation rubric)

tests/
  __init__.py
  conftest.py (pytest fixtures)

.env.example
requirements.txt
pyproject.toml
Dockerfile
docker-compose.yml
```

---

## Part 9: Final Checklist Before You Start

- [ ] Virtual environment created and activated
- [ ] ANTHROPIC_API_KEY set and verified
- [ ] `python cureforge_substrate_init.py` passes all tests
- [ ] Project structure created
- [ ] Git initialized
- [ ] Claude.md read and understood
- [ ] CLAUDE_CODE_QUICK_START.md read
- [ ] Claude Code CLI or Claude.ai ready
- [ ] Requirements.txt template created
- [ ] Pyproject.toml template created

---

## Part 10: Commands You'll Repeat

```bash
# Every Claude Code iteration:

# 1. Run Claude (copy-paste prompt)
# 2. Integrate outputs into app/, tests/
cp [claude_output_files] app/
cp [test_files] tests/

# 3. Type check
mypy app/ --strict

# 4. Lint
ruff check app/

# 5. Test
pytest tests/ -v

# 6. Commit
git add app/ tests/ config/ requirements.txt
git commit -m "M[N]: [Name]"

# 7. Next milestone
# Repeat from step 1
```

---

## Summary: Your Action Items

### RIGHT NOW (Next 30 minutes)

1. ✅ Activate venv: `source venv/bin/activate`
2. ✅ Set ANTHROPIC_API_KEY: `export ANTHROPIC_API_KEY="sk-..."`
3. ✅ Run substrate: `python cureforge_substrate_init.py`
4. ✅ Create structure: `mkdir -p app/{agents,services,api} tests/{unit,integration}`
5. ✅ Initialize Git: `git init && git add . && git commit -m "M0: Scaffold"`

### NEXT 2 HOURS (M2: Channel I/O)

1. ✅ Open Claude Code or Claude.ai
2. ✅ Paste M2 prompt from CLAUDE_CODE_QUICK_START.md
3. ✅ Review Claude's output
4. ✅ Integrate into project: `cp [files] app/`
5. ✅ Run tests: `pytest tests/ -v`
6. ✅ Commit: `git commit -m "M2: Channel I/O"`

### REPEAT FOR M3–M8 (Next 5 days)

Same workflow, different prompts.

### ON DAY 8

Run full E2E test with synthetic candidates. Review security. Deploy.

---

## Questions? Common Answers

**Q: Should I use Antigravity or Claude Code?**
A: Claude Code for this project (already have substrate). Antigravity is for blank projects.

**Q: How long will this take?**
A: ~20–24 hours of Claude + manual integration = production system in 1–1.5 weeks.

**Q: What if Claude generates bad code?**
A: Review against checklist (type hints, tests, audit logging). Ask Claude to fix specific issues.

**Q: Should I commit after every milestone?**
A: Yes. Commit gives you rollback points if needed.

**Q: Can I parallelize milestones?**
A: No. M3 depends on M2, M5 depends on M4. Follow the sequence.

**Q: What if tests fail?**
A: Check the error, ask Claude to fix it, rerun tests. Don't proceed until all pass.

---

**You're ready. Start with STEP 1: Run Substrate. Let's go.** 🚀
