# Claude API Integration Guide for CureForge Pipeline Agent

## Overview

This document specifies how to integrate Claude API into the CureForge recruiting pipeline agent. The system uses Claude as a stateless augmentation layer only—agents do not drive state transitions, write to the database, or make hiring decisions. All outputs are schema-validated before use.

---

## 1. Model Selection & Pinning

### Core Principle
Model versions are pinned in config. Model upgrades are deployment events requiring full test pass and founder approval.

### Agent-to-Model Mapping

| Agent | Model | Rationale | Latency Budget | Cost Per Call |
|-------|-------|-----------|-----------------|--------------|
| Reply Classifier | Claude Haiku (3.5) | High volume (1–5 per candidate), low complexity classification | <2s | ~$0.01 |
| Template Responder | Claude Haiku (3.5) | Template population, no reasoning required | <2s | ~$0.01 |
| Task Decomposer | Claude Sonnet (4) | Moderate reasoning, pattern selection from corpus | <10s | ~$0.10 |
| Evaluation Agent | Claude Opus (4) | Complex reasoning, probe methodology orchestration | <30s | ~$0.50 |
| Offer Drafter | Claude Sonnet (4) | Professional writing, standard task, low complexity | <5s | ~$0.10 |

### Config Example
```python
# config/models.py
MODELS = {
    "classifier": {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 500,
    },
    "templater": {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 1000,
    },
    "decomposer": {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 2000,
    },
    "evaluator": {
        "model": "claude-3-5-opus-20241022",
        "max_tokens": 3000,
    },
    "offer_drafter": {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 1500,
    },
}
```

**Update Cadence**: Check for new models quarterly. Test new model versions in staging before promoting to production.

---

## 2. API Client Setup

### Authentication
- API key stored in secret manager (AWS Secrets Manager / GCP Secret Manager)
- Never in environment variables or code
- Rotated on schedule (30-day cycle minimum)

### Async Client
```python
# services/claude_client.py
import anthropic
import asyncio
from typing import Optional
from app.config import MODELS

class ClaudeClient:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
    
    async def call_agent(
        self,
        agent_name: str,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Non-blocking Claude API call with structured error handling."""
        config = MODELS[agent_name]
        tokens = max_tokens or config["max_tokens"]
        
        try:
            response = self.client.messages.create(
                model=config["model"],
                max_tokens=tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                temperature=temperature,
            )
            return response.content[0].text
        except anthropic.RateLimitError:
            raise  # Propagate for retry logic
        except anthropic.APIError as e:
            log.error(f"Claude API error in {agent_name}: {e}")
            raise

async_client = ClaudeClient(get_secret("claude_api_key"))
```

### Rate Limiting & Retries
Use exponential backoff with jitter. Implement at the Celery task level, not in the client.

```python
@celery_app.task(
    bind=True,
    autoretry_for=(anthropic.RateLimitError,),
    retry_kwargs={"max_retries": 3},
    default_retry_delay=2,  # seconds; doubled on each retry with jitter
)
async def classify_reply(self, candidate_id: str, email_body: str):
    # Task automatically retries on rate limit
    result = await async_client.call_agent("classifier", SYSTEM_PROMPT, email_body)
    return result
```

---

## 3. Agent Contracts & Schemas

### Universal Requirements

1. **JSON-Only Output Enforcement**
   - System prompt explicitly forbids prose, markdown fences, preamble
   - Validation is mandatory before downstream use

2. **Schema Validation**
   - All agent outputs validated against a Pydantic schema
   - Retry once on validation failure
   - Route to founder on second failure with raw output flagged

3. **Immutable Audit Trail**
   - Every API call logged: inputs, outputs, model, timestamp, cost
   - Audit log entries written before downstream actions

### Reply Classifier Contract

**System Prompt**
```
You are an email intent classifier for an engineering recruiting pipeline.

Classify the candidate's email into ONE of these intents:
- INTERESTED: Candidate expresses interest in the role
- QUESTION: Candidate asks clarifying questions
- SCHEDULING: Candidate proposes a meeting or call
- TASK_SUBMISSION: Candidate submits a GitHub repo link for the task
- DECLINE: Candidate declines the opportunity
- OTHER: None of the above; ambiguous

Output ONLY valid JSON, no markdown, no preamble:
{
  "intent": "INTERESTED | QUESTION | SCHEDULING | TASK_SUBMISSION | DECLINE | OTHER",
  "confidence": 0.0,
  "extracted": {
    "questions": ["list of explicit questions if QUESTION intent"],
    "submission_url": "full GitHub URL if TASK_SUBMISSION intent; null otherwise"
  },
  "summary": "one-line internal summary for logging"
}

Be precise. If confidence < 0.75, set intent to OTHER.
```

**Pydantic Schema**
```python
from pydantic import BaseModel, validator

class ReplyClassifierOutput(BaseModel):
    intent: Literal["INTERESTED", "QUESTION", "SCHEDULING", "TASK_SUBMISSION", "DECLINE", "OTHER"]
    confidence: float
    extracted: dict
    summary: str
    
    @validator("confidence")
    def confidence_valid(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be 0.0–1.0")
        return v
```

**Routing Rules**
```python
def route_classified_email(output: ReplyClassifierOutput, candidate_id: str) -> None:
    if output.confidence < 0.75 or output.intent == "OTHER":
        route_to_founder(candidate_id, output, "low_confidence_or_other")
        return
    
    if output.intent == "TASK_SUBMISSION":
        submission_url = output.extracted.get("submission_url")
        if not submission_url:
            route_to_founder(candidate_id, output, "no_url_extracted")
            return
        trigger_submission_intake(candidate_id, submission_url)
    
    elif output.intent == "DECLINE":
        fsm_transition(candidate_id, "WITHDRAWN")
    
    else:  # INTERESTED, QUESTION, SCHEDULING
        trigger_template_responder(candidate_id, output.intent)
```

### Task Decomposer Contract

**System Prompt**
```
You are a task decomposition agent for an engineering recruiting pipeline.

You are given:
1. A CORPUS of current-stage engineering patterns (generic descriptions, no proprietary terms)
2. A BLOCKLIST of frontier/sensitive topics that must never appear in generated tasks
3. ABSTRACTION RULES that strip proprietary nomenclature
4. A candidate ROLE and LEVEL

Your job:
1. Select one engineering pattern from the corpus that exercises the company's engineering discipline
2. Decompose it into a self-contained, sandboxed problem
3. Ensure the problem is abstracted: no internal nomenclature, no proprietary IP, no longevity context
4. Verify the problem is NOT on the blocklist (fail closed: if ambiguous, reject)
5. Emit two outputs:
   - candidate_brief: the problem statement the candidate sees (preamble + problem + deliverable format + submission instructions)
   - internal_spec: expected behavior, held-out tests, known failure modes (NEVER sent to candidate)

Output ONLY valid JSON:
{
  "success": true,
  "corpus_pattern_selected": "pattern_name",
  "abstraction_verified": true,
  "blocklist_check": "PASS",
  "candidate_brief": "full multi-paragraph problem statement",
  "internal_spec": {
    "expected_behavior": "description of correct solution",
    "held_out_tests": [
      {"test_id": "...", "input": "...", "expected_output": "..."}
    ],
    "failure_modes": ["..."]
  }
}

CRITICAL: No timeline in candidate_brief. No rubric language. No internal terminology.
CRITICAL: If the task touches the blocklist and you cannot confirm it is outside, set success=false and explain.
```

**Pydantic Schema**
```python
class HeldOutTest(BaseModel):
    test_id: str
    input: str
    expected_output: str

class InternalSpec(BaseModel):
    expected_behavior: str
    held_out_tests: List[HeldOutTest]
    failure_modes: List[str]

class TaskDecomposerOutput(BaseModel):
    success: bool
    corpus_pattern_selected: str
    abstraction_verified: bool
    blocklist_check: Literal["PASS", "FAIL", "AMBIGUOUS"]
    candidate_brief: str
    internal_spec: Optional[InternalSpec] = None
```

**Routing Rules**
```python
def process_decomposed_task(output: TaskDecomposerOutput, candidate_id: str) -> None:
    if not output.success or output.blocklist_check != "PASS":
        log.error(f"Task rejected: {output.blocklist_check}")
        route_to_founder(candidate_id, output, "task_generation_rejected")
        return
    
    # Draft the task brief for founder approval (default policy)
    draft_template_message(
        candidate_id,
        template_id="task_assignment_cover",
        context={"task_brief": output.candidate_brief},
        send_policy="draft_for_approval"
    )
    
    # Provision GitHub repo with internal spec embedded (hidden from candidate)
    github_url = provision_sandbox_repo(candidate_id, output.internal_spec)
    
    fsm_transition(candidate_id, "TASK_ASSIGNED")
```

### Evaluation Agent Contract

**System Prompt (Simplified Example)**
```
You are the evaluation agent for an engineering recruiting pipeline.

You receive:
1. The candidate's submission source code
2. Structured results from a sandbox execution: held-out test results, metrics, edge-case probes
3. An internal RUBRIC with dimensions and weights (never expose to candidate)

Your job:
1. Analyze the submission against each rubric dimension
2. Score each dimension 0–10 based on EVIDENCE from sandbox results, not code reading alone
3. Compute composite = weighted_sum(dimension_score * weight)
4. Generate a concrete, numbers-backed feedback message (rubric-free) with one specific "upgrade your delivery" request
5. Emit structured evaluation record

RUBRIC (internal only):
- correctness_verification (0.30): Runs, passes held-out probes, math hand-verified
- invariant_failclosed_discipline (0.30): Safe defaults, fail-closed error handling
- structure_determinism (0.15): Clean schemas, deterministic logic
- testing_instrumentation (0.15): Meaningful tests
- communication_iteration (0.10): Explains decisions, responds to feedback

Output ONLY valid JSON:
{
  "dimension_scores": {
    "correctness_verification": 8.5,
    ...
  },
  "composite": 8.2,
  "evidence_summary": "Candidate's solution...",
  "red_flags": ["internal_only_list"],
  "candidate_feedback_draft": "concrete, numbers-backed, no rubric, ends with one specific upgrade ask"
}

CRITICAL: Never expose dimension scores, weights, or red flags to the candidate.
CRITICAL: Feedback must be concrete: "F1 dropped to 0.71 because..." not "good effort but needs work".
```

**Pydantic Schema**
```python
class EvaluationAgentOutput(BaseModel):
    dimension_scores: Dict[str, float]
    composite: float
    evidence_summary: str
    red_flags: List[str]
    candidate_feedback_draft: str
    
    @validator("composite")
    def composite_valid(cls, v):
        if not 0.0 <= v <= 10.0:
            raise ValueError("composite must be 0–10")
        return v
```

---

## 4. Prompt Engineering Patterns

### Rule 1: System Prompt as Contract Specification
System prompts are not suggestions. They are binding specifications. Include:
- Exact output format (JSON schema)
- Exact constraints (no deadlines, no rubric language)
- Decision rules (when to fail-closed)

### Rule 2: Structured Input, Structured Output
Always provide context as structured JSON if possible. Never embed unstructured prose in prompts.

```python
# Good
system = """Classify this email..."""
user_message = json.dumps({
    "email_body": email_text,
    "candidate_name": name,
    "round": 1,
})

# Avoid
system = """Classify this email from {name} on round {round}..."""
user_message = f"""Email: {email_text}"""
```

### Rule 3: Temperature Tuning
- Classification, task decomposition, evaluation: `temperature=0.0` (deterministic)
- Templating, offer drafting: `temperature=0.3` (slightly creative for tone, not content)

### Rule 4: Explicit Constraints in Prompts
State constraints that are hard to validate post-hoc:

```
CONSTRAINT: Do not include:
- Delivery timelines (e.g., "within 7 days", "ASAP")
- Rubric structure or scoring weights
- Internal nomenclature (PatentedAlgorithmName, InternalSystem, LongevityContext)
- Proprietary IP references
```

### Rule 5: Examples in Prompts
Provide 1–2 positive examples of correct output format, especially for edge cases.

```python
user_message = """
Classify these emails:

Email 1: "I'm very interested in the role. When can I start?"
Expected output: {"intent": "INTERESTED", "confidence": 0.99, ...}

Email 2: "Can you clarify what Python version you use?"
Expected output: {"intent": "QUESTION", "confidence": 0.95, "extracted": {"questions": ["Python version?"]}, ...}

Now classify this email:
{actual_email}
"""
```

---

## 5. Cost & Latency Optimization

### Cost Per Candidate
Assume 1–3 evaluation rounds per candidate (best case: hire at round 1; worst case: warm-hold after 3 rounds).

| Agent | Calls Per Candidate | Cost Per Call | Subtotal |
|-------|---------------------|---------------|----------|
| Classifier | 3–5 | $0.01 | ~$0.05 |
| Templater | 3–5 | $0.01 | ~$0.05 |
| Decomposer | 1 | $0.10 | $0.10 |
| Evaluator | 1–3 | $0.50 | $0.50–$1.50 |
| Offer Drafter | 1 | $0.10 | $0.10 |
| **Total per candidate** | — | — | **~$0.80–$1.80** |

**Scaling**: 50 simultaneous candidates ≈ $40–$90/month on Claude API (excluding batch processing discounts).

### Latency SLA
- Classifier: <2s (high volume, responsive)
- Evaluator: <30s (async Celery task, acceptable)
- All others: <10s (non-critical path)

### Batch Processing (Future)
Claude API supports batch processing at lower rates. For non-time-sensitive evaluations:
- Queue evaluation jobs
- Process overnight via Batch API (50% discount)
- Results available next morning

---

## 6. Error Handling & Recovery

### Rate Limiting
Claude API enforces token and request rate limits. Strategy:

1. **Token Rate Limits**
   - Haiku/Sonnet: 100k tokens/min
   - Opus: 50k tokens/min
   - Distribute across time windows

2. **Request Rate Limits**
   - Enforce via Celery task delays
   - Jittered exponential backoff: 2s → 4s → 8s (+ random jitter)

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=1, max=10),
)
async def call_with_retry(agent_name, prompt):
    return await async_client.call_agent(agent_name, prompt)
```

### Schema Validation Failure
If Claude output doesn't match the expected schema:

1. **First Retry**: Resubmit with stricter system prompt + example
2. **Second Failure**: Route to founder with raw output + task flagged

```python
async def call_agent_with_validation(agent_name, prompt, schema):
    for attempt in range(2):
        result = await call_with_retry(agent_name, prompt)
        try:
            validated = schema.parse_raw(result)
            return validated
        except ValidationError as e:
            if attempt == 0:
                # Retry with stricter prompt
                prompt = f"{prompt}\n\nPrevious output was invalid: {e}. Return ONLY the JSON."
            else:
                # Route to human
                route_to_founder(candidate_id, {"raw_output": result, "error": str(e)}, "schema_failure")
                raise
```

### API Outage Handling
If Claude API is down:
- Celery tasks enter dead-letter queue
- Founder is alerted via dashboard
- Evaluations paused; no data loss
- Retry automatically when API recovers

---

## 7. Audit & Compliance

### Logging
Every Claude API call is logged with:
- `timestamp`: ISO 8601
- `candidate_id`: UUID
- `agent_name`: which agent
- `input_tokens`: for cost tracking
- `output_tokens`: for cost tracking
- `model_version`: pinned version
- `output`: raw response (truncated if >1KB)
- `validation_status`: PASSED or FAILED

```python
async def log_claude_call(candidate_id, agent_name, tokens_in, tokens_out, output):
    await db.audit_log.insert({
        "timestamp": now(),
        "candidate_id": candidate_id,
        "event_type": f"claude_call_{agent_name}",
        "actor": "claude_api",
        "inputs": {"agent": agent_name},
        "outputs": {"tokens_in": tokens_in, "tokens_out": tokens_out, "preview": output[:1000]},
    })
```

### Data Privacy
- No candidate PII sent to Claude API except candidate name (if needed for context)
- Email body and submission code are sent (required for classification/evaluation)
- GDPR: Confirm with counsel whether Claude API calls to US-hosted Anthropic servers require Data Processing Agreement

### Cost Monitoring
Track Claude API spend monthly:
- Per-agent breakdown
- Per-candidate cost
- Cost/hire ratio

```python
monthly_claude_cost = sum([
    record.tokens_in * 0.0001 + record.tokens_out * 0.0003
    for record in audit_log if record.event_type.startswith("claude_call_") 
    and record.timestamp >= last_month
])
```

---

## 8. Testing Claude Integration

### Unit Tests
Mock Claude API responses for FSM and schema validation tests.

```python
import unittest.mock as mock

def test_classifier_routes_low_confidence_to_founder():
    with mock.patch("services.claude_client.async_client.call_agent") as mock_call:
        mock_call.return_value = json.dumps({
            "intent": "OTHER",
            "confidence": 0.45,
            "extracted": {},
            "summary": "unclear"
        })
        result = classify_email(candidate_id, email_body)
        assert result == "routed_to_founder"
```

### Integration Tests
Use a staging API key for integration tests. Create synthetic candidates and verify end-to-end flows.

```python
async def test_full_candidate_journey():
    # Add candidate
    candidate = await add_candidate("Test Candidate", "test@example.com")
    
    # Simulate inbound email
    result = await classify_reply(candidate.id, "I'm very interested!")
    assert result.intent == "INTERESTED"
    
    # Verify task was generated
    task = await get_task(candidate.id)
    assert task is not None
    assert "blocklist" not in task.candidate_brief.lower()
```

### Cost Monitoring in Tests
Log token usage in test runs. Flag tests that use >100 tokens per run.

---

## 9. Prompt Evolution & Versioning

### When to Update Prompts
- Rubric weights change → Evaluation Agent prompt updated
- New corpus patterns added → Task Decomposer prompt updated
- Candidate feedback shows misalignment → Check Templater or Evaluator prompts

### Versioning Strategy
Store prompts in version control as separate files, not in code.

```
prompts/
├── classifier.md (v1.2)
├── templater.md (v1.0)
├── decomposer.md (v1.3)
├── evaluator.md (v1.1)
└── offer_drafter.md (v1.0)
```

Prompt changes trigger:
1. Full integration test pass
2. Founder review of example outputs
3. Staged rollout (5 synthetic candidates first)
4. Comparison with previous version (metrics before/after)

---

## 10. Checklist: Before Production Launch

- [ ] All model versions pinned in config.py (no floating versions)
- [ ] Claude API key stored in secret manager, never in code
- [ ] Rate limiting configured at Celery task level
- [ ] Schema validation tests pass for all agents (valid + invalid JSON)
- [ ] Human routing works when confidence < 0.75 or schema validation fails
- [ ] Audit log captures every Claude call with tokens in/out
- [ ] Cost monitoring dashboard shows per-agent breakdown
- [ ] GDPR compliance confirmed with counsel (Claude API calls to US)
- [ ] Dry-run with synthetic candidates and placeholder corpus completes end-to-end
- [ ] Founder approves sample outputs from each agent (classify, task, feedback, offer)

---

## References

- [Claude API Documentation](https://docs.anthropic.com/en/api/getting-started)
- [Prompt Engineering Guide](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview)
- [Vision and Images (if needed for future)](https://docs.anthropic.com/en/docs/vision/vision-overview)

---

**Last Updated**: 2024
**Audience**: Engineering team, DevOps
**Classification**: Internal
