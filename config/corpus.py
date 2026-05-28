from dataclasses import dataclass


@dataclass(frozen=True)
class CorpusPattern:
    id: str
    name: str
    domain: str
    description: str


PATTERNS: dict[str, CorpusPattern] = {
    p.id: p
    for p in [
        # ── Generic distributed-systems patterns (always available) ──────────
        CorpusPattern(
            id="stream_processor",
            name="Stateful Event Stream Processor",
            domain="distributed_systems",
            description=(
                "Design and implement a stateful stream processor that consumes ordered events, "
                "maintains per-key state, and guarantees at-least-once delivery with idempotent "
                "processing. Must handle out-of-order events and late arrivals gracefully."
            ),
        ),
        CorpusPattern(
            id="rate_limiter",
            name="Token Bucket Rate Limiter",
            domain="systems_design",
            description=(
                "Implement a distributed token bucket rate limiter that enforces per-key limits "
                "across multiple service instances. Must be thread-safe, handle clock skew, "
                "and fail open (allow requests) when the limiter itself is unavailable."
            ),
        ),
        CorpusPattern(
            id="data_pipeline",
            name="Fault-Tolerant Data Pipeline",
            domain="data_engineering",
            description=(
                "Build a multi-stage data pipeline that processes records through transformations, "
                "handles partial stage failures with checkpointing, retries idempotently, "
                "and emits a structured error report for records that exhaust retries."
            ),
        ),
        CorpusPattern(
            id="cache_invalidation",
            name="Write-Through Cache with Invalidation",
            domain="distributed_systems",
            description=(
                "Implement a write-through cache layer with event-driven invalidation. "
                "Cache misses must be populated under a per-key lock to prevent thundering herd. "
                "Invalidation events must propagate to all nodes within a bounded time window."
            ),
        ),
        CorpusPattern(
            id="schema_migration",
            name="Zero-Downtime Schema Migration",
            domain="data_engineering",
            description=(
                "Design a zero-downtime schema migration strategy for a high-write table. "
                "Must support dual-write during the migration window, backfill existing rows "
                "without locking, and provide a rollback path if validation fails."
            ),
        ),

        # ── Company-stage patterns (abstracted from current engineering work) ─
        CorpusPattern(
            id="measurement_stream_processor",
            name="Stateful Measurement Stream Processor",
            domain="data_engineering",
            description=(
                "Process an ordered stream of entity measurement events. "
                "For each entity, maintain per-entity state: count, mean, variance, and latest value. "
                "Detect anomalies: flag any value more than 2 standard deviations from the entity's running mean. "
                "Null/missing values must fail closed — emit a structured error record, never silently skip. "
                "Low-quality readings (quality='low' or quality='failed') must be tracked separately "
                "and excluded from statistical aggregation but included in the error report. "
                "Input: list of event dicts with keys entity_id, value, measurement_type, quality. "
                "Output: dict mapping entity_id → {count, mean, variance, latest, anomalies: list, errors: list}. "
                "Edge cases: single-event entity (variance=0.0), all-null entity (error record only)."
            ),
        ),
        CorpusPattern(
            id="pipeline_record_validator",
            name="Multi-Stage Pipeline Record Validator",
            domain="data_engineering",
            description=(
                "Validate a batch of pipeline records against a schema and cross-field invariants. "
                "Each record has: record_id, entity_id, stage (ingestion|validation|transformation), "
                "status (PENDING|COMPLETED|FAILED), payload dict, retry_count. "
                "Validation rules: (1) payload.raw_value must be a non-null float in [0, 100]; "
                "(2) FAILED records must have a non-empty error field; "
                "(3) retry_count must be >= 0 and < 3 for non-FAILED records; "
                "(4) COMPLETED transformation records must have a normalized_value in payload. "
                "Emit a structured validation report: {valid: list[record_id], invalid: list[{record_id, violations: list[str]}], "
                "summary: {total, valid_count, invalid_count}}. "
                "Unknown stage values must fail closed (treated as invalid). Never mutate input records."
            ),
        ),
        CorpusPattern(
            id="checkpoint_simulation_runner",
            name="Checkpointed Multi-Step Simulation Runner",
            domain="agent_systems",
            description=(
                "Implement a multi-step simulation runner that processes a sequence of parameter sets, "
                "applies a deterministic transformation at each step, and supports checkpointing. "
                "A checkpoint records the step index and current accumulated state so the simulation "
                "can resume from the last checkpoint after a failure. "
                "Requirements: each step must be idempotent — replaying it from a checkpoint must "
                "produce the same state as the original run; "
                "if a step raises an exception the runner must record a structured failure entry and "
                "continue (fail-open per step, fail-closed at report time); "
                "the final output must include: completed_steps, failed_steps, final_state, "
                "and a replay_log of checkpoints. "
                "The runner itself must never crash on malformed input — return a structured error record."
            ),
        ),

        # ── CureForge engineering discipline patterns (from build brief) ─────
        CorpusPattern(
            id="explicit_fsm",
            name="Explicit Finite State Machine with Audit Trail",
            domain="agent_systems",
            description=(
                "Implement an explicit finite state machine (FSM) for a multi-stage workflow. "
                "States must be a closed enum; transitions must be defined in a single transition "
                "table (not scattered if/else); every transition must be logged with timestamp, "
                "actor, predicate, from-state, and to-state. Any transition not in the table must "
                "be rejected and logged as an audit event, never silently ignored. "
                "Include at least one predicate-guarded transition (e.g. score >= threshold). "
                "Fail closed: an unknown state or missing predicate must halt, not default."
            ),
        ),
        CorpusPattern(
            id="fail_closed_classifier",
            name="Schema-Validated LLM Classifier with Fail-Closed Routing",
            domain="agent_systems",
            description=(
                "Build a classifier that calls an LLM, validates the response against a strict "
                "Pydantic schema, and routes on the result. Requirements: output must be a closed "
                "enum (no free-form strings in the routing field); confidence < 0.75 or schema "
                "validation failure must route to a human-review queue — never auto-route; "
                "retry once on schema failure with a stricter prompt before escalating; "
                "every call must be logged with model, tokens, latency, and routing decision. "
                "Temperature must be 0.0 for deterministic classification."
            ),
        ),
        CorpusPattern(
            id="immutable_audit_log",
            name="Immutable Append-Only Audit Log with Replay",
            domain="agent_systems",
            description=(
                "Design and implement an immutable append-only audit log for a multi-actor system. "
                "Requirements: entries must never be updated or deleted; each entry must record "
                "timestamp, actor (which agent or user), event_type, and a structured data payload; "
                "the log must support replay from a given timestamp to reconstruct system state; "
                "writes must be atomic (partial writes must not appear as valid entries); "
                "provide a query interface that filters by actor, event_type, and time range "
                "without exposing mutation methods."
            ),
        ),
        CorpusPattern(
            id="sandboxed_code_runner",
            name="Isolated Code Execution Sandbox",
            domain="security_systems",
            description=(
                "Implement a sandboxed code execution runner that accepts untrusted source code, "
                "executes it in an isolated environment, and returns structured results. "
                "Requirements: no network access during execution; enforced CPU, memory, and "
                "time limits; the runner must never mount secrets or host credentials; "
                "capture stdout/stderr and per-test pass/fail results; "
                "return a structured result object (build_status, test_results, metrics, errors) "
                "regardless of whether the code crashes; the runner itself must not crash on "
                "malformed input — fail closed, return a structured error record."
            ),
        ),
        CorpusPattern(
            id="type_enforced_pipeline",
            name="Type-Enforced Multi-Stage Agent Pipeline",
            domain="agent_systems",
            description=(
                "Build a multi-stage processing pipeline where each stage has a typed input "
                "contract and a typed output contract enforced at runtime. Requirements: "
                "each stage must validate its input schema before processing; "
                "stages must be composable without shared mutable state; "
                "a stage failure must not corrupt downstream stages — propagate a typed error "
                "record instead; the pipeline must emit a structured audit event at each stage "
                "boundary with stage name, input hash, output hash, and latency; "
                "closed enumerations for status values — no raw strings."
            ),
        ),
    ]
    
}
