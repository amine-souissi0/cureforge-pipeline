# CureForge Pipeline — Visual Decision Trees & Guides

## Decision Tree 1: Should I Use Claude Code or Antigravity?

```
┌─────────────────────────────────────────────┐
│  Do I have existing substrate (FSM, models)?│
└────────────────────┬────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │ YES                   │ NO
         ▼                       ▼
   ┌──────────────┐    ┌──────────────────┐
   │ Use          │    │ Use ANTIGRAVITY  │
   │ CLAUDE CODE  │    │ first to scaffold│
   │ (THIS YOU)   │    │ then Claude Code │
   └──────────────┘    └──────────────────┘
```

**You are HERE:** ✓ Use CLAUDE CODE exclusively.

---

## Decision Tree 2: Which Tool for Each Task?

```
┌──────────────────────────────────────────┐
│  What task do I need to accomplish?      │
└────────┬──────────────────────────────────┘
         │
    ┌────┴────┬──────────┬──────────┬──────────┐
    │          │          │          │          │
    ▼          ▼          ▼          ▼          ▼
┌─────────┐ ┌──────┐ ┌──────┐ ┌──────────┐ ┌────────┐
│Generate │ │Debug │ │Fix   │ │Understand│ │Optimize│
│code for │ │test  │ │error │ │existing  │ │        │
│milestone│ │fail  │ │      │ │code      │ │        │
└────┬────┘ └──┬───┘ └──┬───┘ └────┬─────┘ └───┬────┘
     │         │        │          │           │
     ▼         ▼        ▼          ▼           ▼
  CLAUDE    pytest    Claude    Claude.md   Claude
  CODE      + print   + review  (read)      (optimize)
```

---

## Decision Tree 3: Paste Full Prompt or Ask Follow-Up?

```
┌─────────────────────────────────────────────┐
│  Claude just generated code.                │
│  Do I understand what it generated?         │
└────────────────────┬────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │ YES                   │ NO
         ▼                       ▼
   ┌──────────────┐    ┌──────────────────────┐
   │ Review for   │    │ Ask Claude:          │
   │ quality:     │    │ "Explain the        │
   │ - Types      │    │  GmailService       │
   │ - Tests      │    │  class. Why use     │
   │ - Logging    │    │  async/await?"      │
   └──────┬───────┘    └──────┬───────────────┘
          │                   │
    ┌─────┴──────────────────┬┘
    │                        │
    ▼                        ▼
  Integrate             Read explanation
                        then Integrate
```

---

## Decision Tree 4: Do I Commit or Fix First?

```
┌─────────────────────────────────────────────┐
│  Did all tests pass?                        │
│  $ pytest tests/ -v                         │
└────────────────────┬────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │ YES                   │ NO
         ▼                       ▼
   ┌──────────────┐    ┌──────────────────────┐
   │ Did mypy and │    │ Ask Claude to fix:   │
   │ ruff pass?   │    │ "Tests failed:       │
   │              │    │  [error message].    │
   │              │    │  Fix it."            │
   └──────┬───────┘    └──────┬───────────────┘
          │                   │
    ┌─────┴──────────────┐    │
    │ YES          NO    │    │
    ▼                ▼   │    │
  COMMIT      Ask Claude │    │
              to add     │    │
              type hints │    │
                  │      │    │
              All fixed? │    │
                  │      │    │
              ┌───┴──────┘    │
              │               │
              ▼               ▼
            COMMIT        FIX AGAIN
```

---

## Decision Tree 5: Should I Ask Claude to Modify Code?

```
┌──────────────────────────────────────────────────┐
│  Do I need to modify code Claude generated?      │
└───────────────────┬──────────────────────────────┘
                    │
        ┌───────────┴───────────────┐
        │                           │
        ▼                           ▼
   ┌─────────────┐         ┌──────────────────┐
   │ Simple      │         │ Complex change   │
   │ (add line)  │         │ (refactor)       │
   └──────┬──────┘         └────────┬─────────┘
          │                         │
          ▼                         ▼
    Do it yourself            Ask Claude:
    (you understand)          "Refactor
                              [module].
                              I need
                              [change]
                              because
                              [reason]."
```

---

## Timeline: M2–M8 Build Schedule

```
Week 1: Foundation & M2–M3
┌─────────────────────────────────────────┐
│ Mon: Run substrate, create structure    │
│      Initialize Git                     │
├─────────────────────────────────────────┤
│ Tue: M2 Prompt → Claude Code            │
│      Integrate, test, commit            │
├─────────────────────────────────────────┤
│ Wed: M3 Prompt → Claude Code            │
│      Integrate, test, commit            │
├─────────────────────────────────────────┤
│ Thu: M4 Prompt → Claude Code            │
│      Integrate, test, commit            │
├─────────────────────────────────────────┤
│ Fri: M5 Prompt → Claude Code            │
│      Integrate, test, commit            │
└─────────────────────────────────────────┘

Week 2: M6–M8 & Hardening
┌─────────────────────────────────────────┐
│ Mon: M6 Prompt → Claude Code            │
│      Integrate, test, commit            │
├─────────────────────────────────────────┤
│ Tue: M7 Prompt → Claude Code            │
│      Integrate, test, commit            │
├─────────────────────────────────────────┤
│ Wed: M8 Prompt → Claude Code            │
│      Integrate, test, commit            │
├─────────────────────────────────────────┤
│ Thu: Security review                    │
│      Dry-run with synthetic candidates  │
├─────────────────────────────────────────┤
│ Fri: Production checklist               │
│      Ready to deploy                    │
└─────────────────────────────────────────┘
```

---

## Efficiency Pyramid

```
                    ▲
                   /│\                DEPLOY (M8)
                  / │ \               (1–2 hours)
                 /  │  \
                /   │   \         M6–M7 (surfaces, loop)
               /    │    \        (4–5 hours)
              /     │     \
             /      │      \     M4–M5 (generation, evaluation)
            /       │       \    (5–6 hours)
           /        │        \
          /         │         \  M2–M3 (I/O, templates)
         /          │          \ (4–5 hours)
        /           │           \
       /            │            \ M1 (substrate) ✓
      /─────────────┼─────────────\ (already done)
     FOUNDATION    INTEGRATION   HARDENING
     
     Effort: Easy | Gradual | Complex
     Success: High | Maintain | Critical
```

---

## File Integration Flow

```
Claude Code Generates
         ↓
  [New Files]
         ↓
    Copy into:
  ┌─────────────────┐
  │   app/agents/   │
  │   app/services/ │
  │   app/api/      │
  │   tests/        │
  └────────┬────────┘
           ↓
    Update:
  ┌─────────────────┐
  │ requirements.txt│
  │ .env.example    │
  └────────┬────────┘
           ↓
      Run Tests:
  ┌─────────────────┐
  │ mypy --strict   │
  │ ruff check      │
  │ pytest          │
  └────────┬────────┘
           ↓
   All Pass? YES
           ↓
    Commit to Git
           ↓
    Next Milestone
```

---

## Error Resolution Flow

```
┌──────────────────────────────────┐
│ ERROR ENCOUNTERED                │
└────────────┬─────────────────────┘
             │
    ┌────────┴──────────────────┐
    │ Type of Error?            │
    └────────┬────────┬────────┬─┴─────────┐
             │        │        │           │
             ▼        ▼        ▼           ▼
        ┌────────┐ ┌───┐ ┌──────┐ ┌─────────────┐
        │Import  │ │Type  │Test │ │Schema      │
        │Error   │ │Error │Fail │ │Validation  │
        └───┬────┘ └──┬──┘ └───┬─┘ └────┬───────┘
            │         │        │        │
      Check: Create   Ask:     Check:  Ask:
      1. Init  Types  "Type    1. Mocks "Add
         files            error:"   in tests  schema
      2. Path           [msg]"  2.Values validation
      3. Import           │    3. Async to [func]"
         name         Ask      await
                      Claude   │
                      │        │
                  All fixed?
                      │
                  YES │
                      ▼
                   CONTINUE
```

---

## Review Checklist (Printable)

```
┌─────────────────────────────────────────────────────┐
│ PRE-CLAUDE CODE CHECKLIST                           │
├─────────────────────────────────────────────────────┤
│ □ Activated venv                                    │
│ □ ANTHROPIC_API_KEY set                            │
│ □ Previous milestone tests pass                    │
│ □ Git status clean                                 │
│ □ Have Claude.md open for reference               │
│ □ Have CLAUDE_CODE_QUICK_START.md open            │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ POST-CLAUDE CODE INTEGRATION CHECKLIST              │
├─────────────────────────────────────────────────────┤
│ □ Files copied to correct directories              │
│ □ mypy --strict passes                             │
│ □ ruff check passes                                │
│ □ pytest tests/ -v passes                          │
│ □ Imports work: python -c "import app"            │
│ □ No hardcoded secrets                             │
│ □ Audit logging present                            │
│ □ Schema validation present                        │
│ □ Type hints on all functions                      │
│ □ >80% test coverage                               │
│ □ No blocking I/O (all async)                      │
│ □ New dependencies in requirements.txt             │
│ □ Ready to commit                                  │
└─────────────────────────────────────────────────────┘
```

---

## Common Workflows (One-Liners)

```bash
# Check if ready for next milestone
mypy app/ --strict && ruff check app/ && pytest tests/ -v && echo "✓ READY"

# Full cleanup and test
find . -type d -name __pycache__ -exec rm -r {} + ; pytest tests/ -v

# View recent commits
git log --oneline -10

# Reset to last commit (undo local changes)
git reset --hard HEAD

# Dry-run before commit
mypy app/ --strict; ruff check app/; pytest tests/ -v

# Install and freeze requirements
pip install -r requirements.txt && pip freeze > requirements.txt
```

---

## Claude Code Efficiency Tips

### Tip 1: Context is King
**Good:**
```
CureForge Pipeline — M2: Channel I/O
[Full spec from CLAUDE_CODE_QUICK_START.md]
Existing: FSM in app/fsm.py, models in app/models.py
Use same async patterns as substrate.
```

**Bad:**
```
Build email classifier
```

### Tip 2: Ask for Tests First
**Good:**
```
Provide:
1. Unit test cases (mock Claude API)
2. Integration test (real Celery, mocked Claude)
3. Source code that passes tests
```

**Bad:**
```
Generate classifier code
```

### Tip 3: Review Before Integrating
**Good:**
```
Claude generates code → Review → Test → Integrate

❌ Reject if:
   - No type hints
   - No tests
   - No audit logging
   - Hardcoded secrets
```

**Bad:**
```
Copy blindly → Integrate → Test later
```

### Tip 4: Ask Clarifying Questions
**Good:**
```
The generated code looks good. One question:
Why use async/await in the email service?
Explain the retry logic.
```

**Bad:**
```
Just take it as-is
```

### Tip 5: Commit Early, Commit Often
**Good:**
```
M2 done → Commit "M2: ..."
M3 done → Commit "M3: ..."
M4 done → Commit "M4: ..."
(9 commits total, one per milestone)
```

**Bad:**
```
Do all 8 milestones → One giant commit
```

---

## Quality Metrics Dashboard

Keep these metrics in mind:

```
┌──────────────────────────────────┐
│ QUALITY METRICS                  │
├──────────────────────────────────┤
│ Test Coverage        : >80% ✓    │
│ Type Safety (mypy)   : STRICT ✓  │
│ Linting (ruff)       : PASS ✓    │
│ Import Clarity       : NO CYCLES │
│ Async Purity         : NO BLOCKS │
│ Audit Logging        : COMPLETE  │
│ Schema Validation    : MANDATORY │
│ Error Handling       : ROUTING   │
│ Secret Management    : EXTERNAL  │
│ Documentation        : PRESENT   │
└──────────────────────────────────┘
```

Target: All green ✓ before committing.

---

## Rollback Procedure (If Something Breaks)

```
Step 1: Identify the problem
  git log --oneline -5
  
Step 2: See what changed
  git diff HEAD~1
  
Step 3: Undo last commit
  git reset --soft HEAD~1
  
Step 4: Undo all changes
  git reset --hard HEAD~1
  
Step 5: Ask Claude to fix and regenerate
  "Last attempt failed: [error].
   Generate [code] differently..."
```

---

## Success Celebrations

```
After M1 (Substrate): ✓ Foundation solid
After M2 (Channel I/O): ✓ Emails working
After M3 (Templating): ✓ Founder queues ready
After M4 (Decomposition): ✓ Tasks generating
After M5 (Evaluation): ✓ Scoring working
After M6 (Loop & Gate): ✓ Full pipeline feedback
After M7 (Surfaces): ✓ Dashboard live
After M8 (Hardening): ✓ PRODUCTION READY 🚀
```

---

**Print this. Reference constantly. Build efficiently.**

**Your next action: Open WORKFLOW_GUIDE.md STEP 1.**
