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
    ]
}
