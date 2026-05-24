from dataclasses import dataclass


@dataclass(frozen=True)
class RubricDimension:
    id: str
    name: str
    weight: float
    description: str


# Weights must sum to 1.0
DIMENSIONS: dict[str, RubricDimension] = {
    d.id: d
    for d in [
        RubricDimension(
            id="correctness_verification",
            name="Correctness & Verification",
            weight=0.30,
            description=(
                "Solution runs, passes held-out probes, and math/logic is hand-verified. "
                "Edge cases handled. No silent failures."
            ),
        ),
        RubricDimension(
            id="invariant_failclosed_discipline",
            name="Invariant & Fail-Closed Discipline",
            weight=0.30,
            description=(
                "Safe defaults everywhere. Errors are explicit and fail-closed. "
                "No hidden state mutations. Invariants documented and enforced."
            ),
        ),
        RubricDimension(
            id="structure_determinism",
            name="Structure & Determinism",
            weight=0.15,
            description=(
                "Clean schema design. Deterministic logic — same inputs produce same outputs. "
                "No unnecessary global state."
            ),
        ),
        RubricDimension(
            id="testing_instrumentation",
            name="Testing & Instrumentation",
            weight=0.15,
            description=(
                "Meaningful unit tests with real assertions. "
                "Edge cases covered. Observable behaviour (logging or metrics)."
            ),
        ),
        RubricDimension(
            id="communication_iteration",
            name="Communication & Iteration",
            weight=0.10,
            description=(
                "Code explains decisions inline where non-obvious. "
                "Candidate responds to feedback constructively."
            ),
        ),
    ]
}

assert abs(sum(d.weight for d in DIMENSIONS.values()) - 1.0) < 1e-9, "Rubric weights must sum to 1.0"


# Decision thresholds — FSM predicates use these
HIRE_THRESHOLD = 8.5       # composite >= 8.5 → HIRE_RECOMMENDED or HIRED
RESUBMIT_THRESHOLD = 7.0   # composite >= 7.0 and < 8.5 → AWAITING_RESUBMISSION
# composite < 7.0 after >= 2 rounds → WARM_HOLD


def compute_composite(dimension_scores: dict[str, float]) -> float:
    """Weighted sum of dimension scores. Unknown dimensions are ignored."""
    total = 0.0
    for dim_id, dim in DIMENSIONS.items():
        score = dimension_scores.get(dim_id, 0.0)
        total += score * dim.weight
    return round(total, 2)
