# CureForge Pipeline Agent — Complete Project Summary & Next Steps

## What You Have

You now have **6 complete files** ready to use:

### 📋 Documentation Files

1. **WORKFLOW_GUIDE.md** (Complete step-by-step guide)
   - Part 1: Understanding your tools (Claude Code vs Antigravity)
   - Part 2: Pre-flight checklist
   - Part 3: Step-by-step workflow (STEPS 1–6)
   - Part 4: Best practices for Claude Code efficiency
   - Part 5: Common issues & solutions
   - Part 6: Antigravity usage (optional)
   - Part 7: Complete workflow at a glance
   - Part 8: Reference guide
   - Part 9: Final checklist
   - Part 10: Commands you'll repeat
   - **STATUS:** READ THIS FIRST. It's your bible.

2. **QUICK_REFERENCE.md** (Cheat sheet for quick lookup)
   - Command cheat sheet (copy-paste ready)
   - Milestone prompts quick links
   - Pre-Claude-Code checklist
   - Post-integration checklist
   - Project structure verification
   - Common issues → solutions (table)
   - Git workflow (simplified)
   - Quality checklist (before committing)
   - **STATUS:** Print this. Keep it nearby.

3. **VISUAL_GUIDES.md** (Decision trees & flowcharts)
   - Decision Tree 1: Claude Code vs Antigravity
   - Decision Tree 2: Which tool for each task
   - Decision Tree 3: Full prompt vs follow-up questions
   - Decision Tree 4: Commit or fix first
   - Decision Tree 5: Modify code or ask Claude
   - Timeline schedule (Week 1 & 2)
   - Efficiency pyramid
   - File integration flow
   - Error resolution flow
   - Printable checklists
   - Efficiency tips (5 key tips)
   - Quality metrics dashboard
   - **STATUS:** Reference when uncertain.

4. **Claude.md** (Claude API Integration Spec)
   - Model selection & pinning (Haiku vs Opus)
   - API client setup with rate limiting
   - Agent contracts & schemas
   - Prompt engineering patterns
   - Cost estimation
   - Error handling & recovery
   - Audit & compliance
   - Testing strategy
   - **STATUS:** Technical reference. Read when generating agents.

5. **CLAUDE_CODE_QUICK_START.md** (Milestone prompts ready to paste)
   - M1: Substrate (already done)
   - M2: Channel I/O (Gmail integration)
   - M3: Templating (template library)
   - M4: Decomposition (task generator)
   - M5: Evaluation (sandbox + scoring)
   - M6: Loop & Gate (feedback controller)
   - M7: Surfaces (dashboard)
   - M8: Hardening (security)
   - **STATUS:** Copy-paste these into Claude Code for each milestone.

### 🔧 Executable Files

6. **cureforge_substrate_init.py** (Runnable foundation)
   - FSM engine with transition table
   - Pydantic data models
   - Schema validators
   - Alembic migration template
   - Unit tests
   - **STATUS:** Run once to verify substrate. Extract classes for app/fsm.py and app/models.py.

---

## Reading Order (Important!)

Read these files in this sequence:

1. **THIS FILE** (you're reading it) — Overview
2. **QUICK_REFERENCE.md** — Get oriented (15 min)
3. **WORKFLOW_GUIDE.md** — PART 1-2 (Pre-flight) — Set up environment (30 min)
4. **WORKFLOW_GUIDE.md** — PART 3 (STEPS 1-6) — Follow step-by-step
5. **CLAUDE_CODE_QUICK_START.md** — Copy prompts as needed
6. **Claude.md** — Reference when reviewing Claude's code (as needed)
7. **VISUAL_GUIDES.md** — Consult when uncertain (as needed)
8. **QUICK_REFERENCE.md** — Keep open while working (always)

---

## Your Immediate Action Plan (Next 30 minutes)

### Phase 1: Environment Setup

```bash
# 1. Activate virtual environment
source venv/bin/activate

# 2. Set ANTHROPIC_API_KEY
export ANTHROPIC_API_KEY="sk-..."

# 3. Verify Claude works
python3 -c "import anthropic; print('Claude API ready')"

# 4. Run substrate test
python cureforge_substrate_init.py

# Expected output: ✓ All tests passed
```

**If substrate test passes:** Proceed to Phase 2. **If it fails:** Debug (see QUICK_REFERENCE.md).

### Phase 2: Project Structure

```bash
# Create directories
mkdir -p app/{agents,services,api,models}
mkdir -p tests/{unit,integration,e2e}
mkdir -p config prompts migrations docker

# Create config files
touch .env.example requirements.txt pyproject.toml .gitignore

# Initialize Git
git init
git config user.name "Your Name"
git config user.email "you@example.com"
git add .
git commit -m "M0: Project scaffold + substrate"
```

### Phase 3: Read & Familiarize

```bash
# Read these files in your editor
# 1. QUICK_REFERENCE.md (15 min)
# 2. WORKFLOW_GUIDE.md Part 1-2 (15 min)
```

**Total time: ~30 min. Then you're ready for STEP 1 in WORKFLOW_GUIDE.md.**

---

## Next 2 Weeks at a Glance

### Week 1: Foundation & Core Milestones

| Day | Milestone | Tasks | Duration |
|-----|-----------|-------|----------|
| **Mon** | Substrate ✓ | Verify locally | 30 min |
| **Mon** | Structure | Create directories, git init | 15 min |
| **Mon** | Familiarize | Read guides | 30 min |
| **Tue** | M2 (I/O) | Claude prompt → integrate → test → commit | 2–3 h |
| **Wed** | M3 (Templates) | Claude prompt → integrate → test → commit | 2–3 h |
| **Thu** | M4 (Decomposition) | Claude prompt → integrate → test → commit | 2.5–3 h |
| **Fri** | M5 (Evaluation) | Claude prompt → integrate → test → commit | 2.5–3 h |

### Week 2: Advanced Milestones & Hardening

| Day | Milestone | Tasks | Duration |
|-----|-----------|-------|----------|
| **Mon** | M6 (Loop & Gate) | Claude prompt → integrate → test → commit | 2–3 h |
| **Tue** | M7 (Surfaces) | Claude prompt → integrate → test → commit | 2–3 h |
| **Wed** | M8 (Hardening) | Claude prompt → integrate → test → commit | 2–3 h |
| **Thu** | Security Review | Run security tests, audit completeness | 2–3 h |
| **Fri** | Dry-Run & Deploy | Full E2E test with synthetic candidates | 2–3 h |

**Total: ~20–25 hours of work → Production system in 2 weeks**

---

## Success Criteria (Milestone Checklist)

After each milestone, verify:

```
✅ Claude code integrated into app/
✅ Tests pass: pytest tests/ -v
✅ Type check passes: mypy app/ --strict
✅ Linting passes: ruff check app/
✅ Audit logging present
✅ Schema validation present
✅ No hardcoded secrets
✅ Committed: git commit -m "M[N]: [Name]"
```

**If all ✅: Proceed to next milestone. If any ❌: Fix before proceeding.**

---

## Claude Code Workflow (Repeat for M2–M8)

```
1. OPEN Claude Code or Claude.ai
   └─ Claude Code CLI (recommended)
      or Claude.ai web (alternative)

2. COPY PROMPT from CLAUDE_CODE_QUICK_START.md
   └─ M2, M3, M4, M5, M6, M7, or M8 section

3. PASTE into Claude
   └─ Add context: "Existing code in app/, tests/"

4. REVIEW OUTPUT
   └─ Check: type hints, tests, logging, no secrets

5. INTEGRATE
   └─ Copy files into app/, tests/
   └─ Update requirements.txt

6. TEST
   └─ mypy app/ --strict
   └─ ruff check app/
   └─ pytest tests/ -v

7. COMMIT
   └─ git add app/ tests/ config/ requirements.txt
   └─ git commit -m "M[N]: [Milestone Name]"

8. NEXT
   └─ Repeat for M[N+1]
```

**Time per milestone: 2–3 hours**

---

## Key Files You'll Edit Manually

```
app/
  __init__.py         (import declarations)
  main.py             (FastAPI app)
  database.py         (SQLAlchemy setup)
  fsm.py              (from substrate - FSM engine)
  models.py           (from substrate - Pydantic models)
  config.py           (local configuration)

config/
  models.py           (Claude model versions - PIN THESE)
  templates.py        (template definitions)
  corpus.yaml         (task patterns - founder supplies)
  rubric.yaml         (evaluation rubric - founder supplies)

requirements.txt      (Python dependencies)
pyproject.toml        (project metadata)
.env.example          (environment variables)
.gitignore            (ignore patterns)
```

**Claude generates most of the rest.** You orchestrate.

---

## Files Claude WILL Generate (Per Milestone)

**M2 (Channel I/O):**
```
app/services/gmail_service.py
app/agents/reply_classifier.py
app/services/send_policy.py
app/api/webhooks.py
app/celery.py (or app/workers/)
tests/unit/test_classifier.py
tests/integration/test_gmail.py
README_M2.md
```

**M3 (Templating):**
```
app/templates/__init__.py
app/agents/template_responder.py
app/services/approval_queue.py
app/api/templates.py
tests/test_templates.py
```

**M4–M8:** Similar pattern (agents, services, APIs, tests)

---

## Critical Constraints (Never Violate)

From Build Brief § sections:

| Constraint | Section | Check |
|-----------|---------|-------|
| No LinkedIn automation | §3.1 | Not in code ✓ |
| Sandbox isolation | §3.2 | Docker + network-disabled ✓ |
| No proprietary IP exposed | §3.3 | Abstraction rules enforced ✓ |
| Blocklist fail-closed | §3.4 | Ambiguous → reject ✓ |
| Rubric never exposed | §3.5 | Not in candidate messages ✓ |
| Human gate by default | §3.6 | HITL toggles ✓ |
| Warm-hold not cold rejection | §3.7 | Relationship-preserving ✓ |
| No deadlines on candidates | §3.8 | No "within 7 days" ✓ |
| Full audit trail | §3.9 | Every action logged ✓ |

**Review code against these before committing.**

---

## What If Something Goes Wrong?

### Issue Type 1: Import/Environment Errors
```
Error: ModuleNotFoundError: No module named 'app.services'
Solution: mkdir -p app/services && touch app/services/__init__.py
```

### Issue Type 2: Type Errors
```
Error: mypy reports "Argument has incompatible type"
Solution: Ask Claude: "mypy error: [message]. Fix type hints."
```

### Issue Type 3: Test Failures
```
Error: FAILED tests/unit/test_classifier.py
Solution: pytest tests/unit/test_classifier.py -v -s (debug output)
         Ask Claude to fix
```

### Issue Type 4: Schema Validation
```
Error: ValidationError on Claude output
Solution: Ask Claude: "Output doesn't match schema. Regenerate."
```

**See QUICK_REFERENCE.md** for more solutions.

---

## Rollback Procedure (If Needed)

```bash
# View recent commits
git log --oneline -5

# See what changed in last commit
git show HEAD

# Undo last commit, keep changes
git reset --soft HEAD~1

# Undo last commit, discard changes
git reset --hard HEAD~1

# Then ask Claude to regenerate
```

---

## Tools You're Using

### Claude Code (Primary)
- Generates code for each milestone
- Refines on request
- Best for: iterative development

### Claude.ai (Alternative)
- Same as Claude Code but in web browser
- If Claude Code CLI has issues, use this

### Antigravity (Optional)
- For initial scaffold (you already have this)
- For boilerplate generation (docker, etc.)
- **Skip for this project** (you have substrate)

### Pytest (Testing)
```bash
pytest tests/ -v          # All tests
pytest tests/unit/ -v     # Unit tests
pytest tests/integration/ # Integration tests
pytest tests/ -v -s       # Verbose with print output
```

### Mypy (Type Checking)
```bash
mypy app/ --strict        # Strict mode (required)
mypy app/models.py        # Single file
```

### Ruff (Linting)
```bash
ruff check app/           # Check
ruff check --fix app/     # Auto-fix
```

### Git (Version Control)
```bash
git status                # See changes
git add .                 # Stage all
git commit -m "message"   # Commit
git log --oneline         # View history
git reset --hard HEAD~1   # Undo last commit
```

---

## Success Looks Like

### After M1 (Substrate)
```
✓ cureforge_substrate_init.py runs
✓ All tests pass
✓ FSM transition table works
✓ Pydantic schemas validated
```

### After M2 (Channel I/O)
```
✓ Gmail OAuth2 integrated
✓ Emails classified automatically
✓ Send policy working (auto/draft)
✓ Tests pass, no secrets in code
```

### After M3–M7
```
✓ Each milestone builds on previous
✓ Full audit trail present
✓ No constraint violations (§3.1–3.9)
✓ All tests passing
```

### After M8 (Hardening)
```
✓ Security review complete
✓ Sandbox isolation verified
✓ Full E2E test with synthetic candidates
✓ Production checklist signed off
✓ READY TO DEPLOY 🚀
```

---

## Next Steps (Immediate)

### NOW (Next 30 min)
1. Open terminal
2. Activate venv: `source venv/bin/activate`
3. Run substrate: `python cureforge_substrate_init.py`
4. Verify: "✓ All tests passed"
5. Create structure: `mkdir -p app/{agents,services,api} tests/{unit,integration,e2e}`
6. Initialize Git: `git init && git commit -m "M0: Scaffold"`

### IN 1 HOUR
1. Read QUICK_REFERENCE.md (15 min)
2. Read WORKFLOW_GUIDE.md Part 1-2 (15 min)
3. Ready for STEP 1

### THIS WEEK
1. Follow WORKFLOW_GUIDE.md STEP by STEP
2. Complete M2 (Channel I/O) by Wednesday
3. Complete M3 (Templating) by Friday

### NEXT WEEK
1. Complete M4–M5 (Decomposition & Evaluation)
2. Complete M6–M7 (Loop & Surfaces)
3. Complete M8 (Hardening)
4. Full E2E test
5. **DEPLOY**

---

## File Reference Chart

| File | Purpose | Read When | Keep Open |
|------|---------|-----------|-----------|
| WORKFLOW_GUIDE.md | Step-by-step guide | Starting | During work |
| QUICK_REFERENCE.md | Commands, checklists | Before/after Claude | Always |
| VISUAL_GUIDES.md | Decision trees | When uncertain | As needed |
| Claude.md | API spec | Reviewing code | During M2–M8 |
| CLAUDE_CODE_QUICK_START.md | Milestone prompts | For each M | When pasting |
| cureforge_substrate_init.py | Foundation | Once (first) | Archived |

---

## Efficiency Tips (Top 5)

1. **Context is everything.** Full spec → Claude generates better code.
2. **Test immediately.** Don't wait. Run tests after each integration.
3. **Commit often.** 9 commits (one per milestone) > 1 giant commit.
4. **Ask for clarification.** If unclear, ask Claude. Takes 2 min, saves 30 min.
5. **Reference constraints.** Before committing, verify no §3 violations.

---

## Final Checklist Before You Start

- [ ] Python 3.10+ installed
- [ ] Virtual environment created and activated
- [ ] ANTHROPIC_API_KEY set and verified
- [ ] cureforge_substrate_init.py runs successfully
- [ ] All substrate tests pass
- [ ] Project directories created
- [ ] Git initialized
- [ ] WORKFLOW_GUIDE.md printed or open
- [ ] QUICK_REFERENCE.md printed or open
- [ ] CLAUDE_CODE_QUICK_START.md open
- [ ] Claude Code or Claude.ai ready
- [ ] 2 weeks blocked on your calendar
- [ ] You've read WORKFLOW_GUIDE.md Part 1-2

---

## Questions? Answers Here

**Q: Should I use Antigravity or Claude Code?**
A: Claude Code. You have substrate already.

**Q: How long will this take?**
A: ~20–25 hours of work. 1–1.5 weeks if focused.

**Q: Can I parallelize milestones?**
A: No. M3 needs M2, M5 needs M4. Follow sequence.

**Q: What if Claude generates bad code?**
A: Review against checklist. Ask Claude to fix. Iterate.

**Q: What if a test fails?**
A: Read error, ask Claude, rerun. Don't proceed until passing.

**Q: Can I skip milestones?**
A: No. Each is a dependency for the next.

**Q: How much of this is actually Claude doing?**
A: ~70% of code generation. You do 30% (structure, integration, verification).

**Q: Am I ready?**
A: If you've run substrate successfully and read QUICK_REFERENCE.md: YES.

---

## Your Command

You have everything needed. The path is clear. The documentation is complete. The tools are ready.

**Your next action: Open terminal. Activate venv. Run substrate. Check for ✓.**

**Then follow WORKFLOW_GUIDE.md STEP 1.**

**Build time: 2 weeks. Production system: Ready to deploy.**

**Let's ship this.** 🚀

---

## Document Map

```
📁 outputs/
├── Claude.md                      (API spec)
├── cureforge_substrate_init.py    (Foundation)
├── CLAUDE_CODE_QUICK_START.md     (Milestone prompts)
├── WORKFLOW_GUIDE.md              (Complete guide) ← START HERE
├── QUICK_REFERENCE.md             (Cheat sheet) ← KEEP OPEN
├── VISUAL_GUIDES.md               (Decision trees)
└── PROJECT_SUMMARY.md             (This file)
```

**All files cross-reference. Print, bookmark, reference constantly.**

---

**Status: READY TO BUILD**

**You have 6 complete files. You have a 2-week plan. You have decision trees. You have checklists.**

**Next action: Open WORKFLOW_GUIDE.md and follow STEP 1.**

**Time to build.** ⏱️ 🚀
