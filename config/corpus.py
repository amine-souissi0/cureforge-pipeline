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
