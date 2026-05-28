from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.fsm import CandidateState
from config.rubric import HIRE_THRESHOLD, RESUBMIT_THRESHOLD

MAX_RESUBMISSION_ROUNDS = 2
IMPROVEMENT_MIN_DELTA = 0.3  # at least 0.3 gain between rounds to count as improving


@dataclass
class Decision:
    next_state: CandidateState
    reasoning: str
    requires_founder_approval: bool
    fsm_context: Dict[str, Any]


def compute_trajectory(composites: List[float]) -> str:
    """
    Return 'improving', 'stable', or 'declining' based on round-over-round deltas.

    - improving: latest round improved by >= IMPROVEMENT_MIN_DELTA over previous
    - declining: latest round dropped vs previous
    - stable: change is within +/- IMPROVEMENT_MIN_DELTA (flat)
    Single-round history always returns 'stable'.
    """
    if len(composites) < 2:
        return "stable"
    delta = composites[-1] - composites[-2]
    if delta >= IMPROVEMENT_MIN_DELTA:
        return "improving"
    if delta < 0:
        return "declining"
    return "stable"


def is_stagnating(composites: List[float]) -> bool:
    """
    True if there are >= 2 rounds and no round showed meaningful improvement.
    Used to gate the warm-hold path: candidate tried multiple rounds but didn't grow.
    """
    if len(composites) < 2:
        return False
    return all(
        composites[i + 1] - composites[i] < IMPROVEMENT_MIN_DELTA
        for i in range(len(composites) - 1)
    )


def decide(
    composite: float,
    rounds_completed: int,
    mode: str = "recommend",
    prior_composites: List[float] | None = None,
) -> Decision:
    """
    Pure decision function — no side effects, no I/O.

    Maps composite score + trajectory + round count to the next FSM state.

    Args:
        composite: weighted composite score 0–10 for the latest round
        rounds_completed: total evaluation rounds completed (includes latest)
        mode: "recommend" (founder approves hire) or "autonomous" (auto-hire)
        prior_composites: all composite scores in order, oldest first, INCLUDING the latest

    Returns:
        Decision with next_state, reasoning, and FSM context dict.
    """
    history = prior_composites or [composite]
    trajectory = compute_trajectory(history)
    stagnating = is_stagnating(history)

    # ── Hire path ────────────────────────────────────────────────────────────
    # §9: composite >= hire_threshold AND stable or improving trajectory
    if composite >= HIRE_THRESHOLD and trajectory != "declining":
        if mode == "autonomous":
            return Decision(
                next_state=CandidateState.HIRED,
                reasoning=(
                    f"Composite {composite:.2f} ≥ {HIRE_THRESHOLD}, trajectory={trajectory} — "
                    "auto-hire (autonomous mode)."
                ),
                requires_founder_approval=False,
                fsm_context={"composite": composite, "mode": "autonomous", "trajectory": trajectory},
            )
        return Decision(
            next_state=CandidateState.HIRE_RECOMMENDED,
            reasoning=(
                f"Composite {composite:.2f} ≥ {HIRE_THRESHOLD}, trajectory={trajectory} — "
                "hire recommended, awaiting founder confirmation."
            ),
            requires_founder_approval=True,
            fsm_context={"composite": composite, "mode": "recommend", "trajectory": trajectory},
        )

    # Composite meets threshold but score is declining across rounds — resubmit, don't hire yet
    if composite >= HIRE_THRESHOLD and trajectory == "declining":
        return Decision(
            next_state=CandidateState.AWAITING_RESUBMISSION,
            reasoning=(
                f"Composite {composite:.2f} ≥ {HIRE_THRESHOLD} but trajectory is declining "
                f"({history}) — one resubmission to confirm stable output."
            ),
            requires_founder_approval=False,
            fsm_context={"composite": composite, "trajectory": trajectory},
        )

    # ── Warm-hold path ───────────────────────────────────────────────────────
    # §9: below 7.0 across rounds with no improvement → warm hold
    if composite < RESUBMIT_THRESHOLD and (
        stagnating or rounds_completed >= MAX_RESUBMISSION_ROUNDS
    ):
        return Decision(
            next_state=CandidateState.WARM_HOLD,
            reasoning=(
                f"Composite {composite:.2f} < {RESUBMIT_THRESHOLD} after {rounds_completed} round(s), "
                f"trajectory={trajectory} — no improvement path. Moving to warm hold."
            ),
            requires_founder_approval=False,
            fsm_context={"composite": composite, "rounds": rounds_completed, "trajectory": trajectory},
        )

    # ── Resubmit path ────────────────────────────────────────────────────────
    return Decision(
        next_state=CandidateState.AWAITING_RESUBMISSION,
        reasoning=(
            f"Composite {composite:.2f} in [{RESUBMIT_THRESHOLD}, {HIRE_THRESHOLD}), "
            f"trajectory={trajectory}, round {rounds_completed} — "
            "resubmission opportunity granted."
        ),
        requires_founder_approval=False,
        fsm_context={"composite": composite, "rounds": rounds_completed, "trajectory": trajectory},
    )
