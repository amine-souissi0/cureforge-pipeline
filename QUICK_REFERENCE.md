# CureForge Pipeline — Quick Reference Card

## Command Cheat Sheet

### Environment Setup (One Time)
```bash
# Create virtual environment
python3.11 -m venv venv

# Activate
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Set API key
export ANTHROPIC_API_KEY="sk-..."

# Verify Claude access
python3 -c "import anthropic; print('Ready')"
```

### Substrate Verification (One Time)
```bash
# Run substrate initialization
python cureforge_substrate_init.py

# Expected output: ✓ All tests passed
```

### For Each Milestone (M2–M8)

```bash
# 1. COPY & PASTE PROMPT
# Open Claude Code or Claude.ai
# Paste prompt from CLAUDE_CODE_QUICK_START.md

# 2. INTEGRATE OUTPUT
mkdir -p app/{agents,services,api}
cp [claude_output_files] app/
cp [test_files] tests/

# 3. TYPE CHECK
mypy app/ --strict

# 4. LINT
ruff check app/

# 5. TEST
pytest tests/ -v
pytest tests/unit/ -v       # Unit tests only
pytest tests/integration/ -v # Integration tests only
pytest tests/e2e/ -v        # End-to-end tests only

# 6. COMMIT
git add app/ tests/ config/ requirements.txt
git commit -m "M[N]: [Milestone Name]"

# Example: M2 commit
git commit -m "M2: Channel I/O - Gmail, classifier, send policy"
```

### Debugging Commands

```bash
# Check Python environment
which python
python --version

# List installed packages
pip list

# Reinstall dependencies
pip install -r requirements.txt

# Clean up cache
find . -type d -name __pycache__ -exec rm -r {} +
rm -rf .pytest_cache

# Git status
git status
git log --oneline

# Find type errors
mypy app/ --strict

# Find linting issues
ruff check app/

# Run tests with verbose output
pytest tests/ -v -s

# Run specific test
pytest tests/unit/test_classifier.py::test_high_confidence -v
```

---

## Milestone Prompts Quick Links

| M | Name | Where to Find | Time |
|---|------|---------------|------|
| 1 | ✅ Substrate | cureforge_substrate_init.py | Done |
| 2 | Channel I/O | CLAUDE_CODE_QUICK_START.md (Phase 5) | 2h |
| 3 | Templating | CLAUDE_CODE_QUICK_START.md (Phase 5) | 2h |
| 4 | Decomposition | CLAUDE_CODE_QUICK_START.md (Phase 6) | 2.5h |
| 5 | Evaluation | CLAUDE_CODE_QUICK_START.md (Phase 6) | 2.5h |
| 6 | Loop & Gate | CLAUDE_CODE_QUICK_START.md (Phase 6) | 2h |
| 7 | Surfaces | CLAUDE_CODE_QUICK_START.md (Phase 6) | 2.5h |
| 8 | Hardening | CLAUDE_CODE_QUICK_START.md (Phase 6) | 3h |

---

## Pre-Claude-Code Checklist

Before pasting ANY prompt into Claude:

- [ ] Activate venv: `source venv/bin/activate`
- [ ] Set API key: `export ANTHROPIC_API_KEY="sk-..."`
- [ ] Previous milestone tests pass: `pytest tests/ -v`
- [ ] Git is clean: `git status` (no uncommitted changes)
- [ ] Claude.md reference nearby (for API details)
- [ ] Have CLAUDE_CODE_QUICK_START.md open

---

## Post-Claude-Code Integration Checklist

After Claude generates code, before committing:

- [ ] Copy files into correct directories
- [ ] Type hints pass: `mypy app/ --strict`
- [ ] Linting passes: `ruff check app/`
- [ ] Unit tests pass: `pytest tests/unit/ -v`
- [ ] Integration tests pass: `pytest tests/integration/ -v`
- [ ] Imports work: `python -c "import app; print('OK')"`
- [ ] New dependencies in requirements.txt: `pip freeze > requirements.txt`
- [ ] No hardcoded secrets in code
- [ ] Audit logging present on state changes
- [ ] Schema validation on all Claude API outputs
- [ ] Git status clean: `git status`
- [ ] Commit message follows pattern: `git commit -m "M[N]: [Name]"`

---

## Project Structure Verification

Run this to verify structure is correct:

```bash
tree app/ tests/ config/
# or
find app tests config -type f -name "*.py" | head -20
```

**Expected structure:**
```
app/
├── __init__.py
├── main.py
├── models.py        (Pydantic models)
├── fsm.py           (FSM engine)
├── database.py
├── config.py
├── celery.py        (if M2+)
├── agents/
│   ├── __init__.py
│   ├── reply_classifier.py    (M2)
│   ├── template_responder.py  (M3)
│   ├── task_decomposer.py     (M4)
│   ├── evaluation_agent.py    (M5)
│   └── offer_drafter.py       (M7)
├── services/
│   ├── __init__.py
│   ├── gmail_service.py       (M2)
│   ├── send_policy.py         (M2/M3)
│   ├── approval_queue.py      (M3)
│   ├── github_service.py      (M4)
│   ├── task_service.py        (M4)
│   ├── sandbox_runner.py      (M5)
│   ├── evaluation_service.py  (M5/M6)
│   ├── feedback_controller.py (M6)
│   └── decision_gate.py       (M6)
└── api/
    ├── __init__.py
    ├── webhooks.py      (M2)
    ├── candidates.py    (M2)
    ├── templates.py     (M3)
    ├── tasks.py         (M4)
    ├── evaluations.py   (M5)
    └── dossier.py       (M7)

tests/
├── __init__.py
├── conftest.py
├── unit/
│   ├── test_fsm.py
│   ├── test_classifier.py     (M2)
│   ├── test_templates.py      (M3)
│   └── ...
├── integration/
│   ├── test_gmail.py          (M2)
│   ├── test_decomposer.py     (M4)
│   └── ...
└── e2e/
    └── test_full_pipeline.py (M8)

config/
├── __init__.py
├── models.py       (Claude model versions)
├── templates.py    (Template definitions)
├── corpus.yaml     (Task patterns)
└── rubric.yaml     (Evaluation rubric)
```

---

## Common Issues → Solutions

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: app.services` | `touch app/services/__init__.py` |
| `mypy errors: "Any" type hints` | Ask Claude: "Add strict type hints to [function]" |
| `Tests fail after integration` | `pytest tests/ -v -s` (verbose), check error, ask Claude to fix |
| `"No module named anthropic"` | `pip install anthropic` |
| `ANTHROPIC_API_KEY not set` | `export ANTHROPIC_API_KEY="sk-..."` |
| `git commit fails` | `git status`, resolve conflicts or uncommitted changes |
| `Import cycles detected` | Ask Claude: "Refactor [module] to remove circular imports" |
| `No audit logging found` | Ask Claude to add audit log entries to all state changes |

---

## Git Workflow (Simplified)

```bash
# Check status
git status

# Stage all changes
git add .

# Commit with milestone
git commit -m "M2: Channel I/O - Gmail OAuth, classifier"

# View log
git log --oneline -10

# Undo last commit (if needed)
git reset --soft HEAD~1
```

---

## Milestone Dependencies

```
M1 (Substrate) ✅
  ↓
M2 (Channel I/O) — Gmail, classifier, send policy
  ↓
M3 (Templating) — Template library, responder
  ↓
M4 (Decomposition) — Task generator, GitHub
  ↓
M5 (Evaluation) — Sandbox, scoring
  ↓
M6 (Loop & Gate) — Feedback, decision
  ↓
M7 (Surfaces) — Dashboard, offer drafter
  ↓
M8 (Hardening) — Security, E2E tests
```

**IMPORTANT:** Do NOT skip milestones or run in parallel. Each depends on the previous.

---

## Key Constraints to Remember

When reviewing Claude's output, verify:

| Constraint | Reference | Check |
|-----------|-----------|-------|
| No LinkedIn automation | §3.1 | Not in code ✓ |
| Candidate code sandboxed | §3.2 | Docker isolation ✓ |
| No proprietary IP exposed | §3.3 | Abstraction in decomposer ✓ |
| Frontier blocklist enforced | §3.4 | Fail-closed logic ✓ |
| Rubric never exposed | §3.5 | No rubric in candidate messages ✓ |
| Human gate by default | §3.6 | HITL toggles ✓ |
| Warm-hold not cold rejection | §3.7 | Relationship-preserving messages ✓ |
| No deadlines on candidates | §3.8 | No "within 7 days" language ✓ |
| Full audit trail | §3.9 | Every action logged ✓ |

---

## Quality Checklist (Before Committing)

```
Code Quality
  [ ] Strict type hints (mypy --strict passes)
  [ ] No `Any` types unless justified
  [ ] Async/await used throughout
  [ ] No blocking I/O calls
  
Testing
  [ ] >80% code coverage
  [ ] Unit tests pass
  [ ] Integration tests pass
  [ ] Mock external services
  
Security
  [ ] No hardcoded secrets
  [ ] Secrets in secret manager
  [ ] Audit logging on state changes
  [ ] Schema validation on inputs
  
Documentation
  [ ] Docstrings on public functions
  [ ] Type hints on all parameters
  [ ] Comments on complex logic
  
FSM
  [ ] All transitions logged
  [ ] Predicates tested
  [ ] Invalid transitions rejected
  
Audit
  [ ] Every API call logged
  [ ] Every email send/receive logged
  [ ] Every state change logged
  [ ] Timestamps ISO 8601
  
Constraints
  [ ] No rubric in candidate output
  [ ] No deadlines in messages
  [ ] No proprietary IP in tasks
  [ ] Blocklist enforced (fail-closed)
```

---

## Claude Code Prompt Template

Copy this template when asking Claude for help:

```
You are building CureForge Pipeline Agent.

CONTEXT:
- Existing code in app/, tests/
- Substrate complete (M1)
- [Previous milestones complete if applicable]

TASK:
[What to build - copy from CLAUDE_CODE_QUICK_START.md]

CONSTRAINTS:
- §3.5: No rubric in candidate-facing output
- §3.8: No deadlines in messages
- §3.9: Audit logging on every action

REQUIREMENTS:
- Strict type hints (mypy --strict)
- >80% test coverage
- Schema validation on Claude outputs
- Error handling with human routing

PROVIDE:
1. [File 1]
2. [File 2]
3. Tests
4. .env.example (updated)
5. README (setup instructions)
```

---

## URLs & References

- **Claude.md** — API integration spec
- **CLAUDE_CODE_QUICK_START.md** — Milestone prompts
- **WORKFLOW_GUIDE.md** — Complete step-by-step guide (this file)
- **Build Brief** — CureForge_Recruiting_Pipeline_Agent_Build_Brief__1_.pdf
- **Architecture** — CureForge_AI_Architecture_Blueprint.docx

---

## Success Criteria (Per Milestone)

Each milestone is done when:

- ✅ Claude code integrated into project
- ✅ All tests pass (`pytest tests/ -v`)
- ✅ Type check passes (`mypy app/ --strict`)
- ✅ Linting passes (`ruff check app/`)
- ✅ Audit logging present
- ✅ Schema validation present
- ✅ No hardcoded secrets
- ✅ Committed to git with message: `M[N]: [Name]`

---

## Final Milestone Sequence (Copy This)

```bash
# M2: 2 hours
# [ ] Paste M2 prompt
# [ ] Integrate, test, commit

# M3: 2 hours  
# [ ] Paste M3 prompt
# [ ] Integrate, test, commit

# M4: 2.5 hours
# [ ] Paste M4 prompt
# [ ] Integrate, test, commit

# M5: 2.5 hours
# [ ] Paste M5 prompt
# [ ] Integrate, test, commit

# M6: 2 hours
# [ ] Paste M6 prompt
# [ ] Integrate, test, commit

# M7: 2.5 hours
# [ ] Paste M7 prompt
# [ ] Integrate, test, commit

# M8: 3 hours
# [ ] Paste M8 prompt
# [ ] Integrate, test, commit
# [ ] Full E2E test
# [ ] Security review
# [ ] Production checklist

# DONE: 20–24 hours
```

---

**Ready to build? Follow WORKFLOW_GUIDE.md STEP by STEP.**

**Questions? Ask Claude or refer to Build Brief § sections.**

**Let's ship this.** 🚀
