from dataclasses import dataclass
from typing import Any, Dict

from app.fsm import CandidateState
from config.rubric import HIRE_THRESHOLD, RESUBMIT_THRESHOLD

MAX_RESUBMISSION_ROUNDS = 2


@dataclass
class Decision:
    next_state: CandidateState
    reasoning: str
    requires_founder_approval: bool
    fsm_context: Dict[str, Any]


def decide(
    composite: float,
    rounds_completed: int,
    mode: str = "recommend",
) -> Decision:
    """
    Pure decision function — no side effects, no I/O.

    Maps composite score + round count to the next FSM state.

    Args:
        composite: weighted composite score 0–10
        rounds_completed: how many evaluation rounds this candidate has had
        mode: "recommend" (founder approves hire) or "autonomous" (auto-hire)

    Returns:
        Decision with next_state, human-readable reasoning, and FSM context dict.
    """
    if composite >= HIRE_THRESHOLD:
        if mode == "autonomous":
            return Decision(
                next_state=CandidateState.HIRED,
                reasoning=f"Composite {composite:.2f} ≥ {HIRE_THRESHOLD} — auto-hire (autonomous mode).",
                requires_founder_approval=False,
                fsm_context={"composite": composite, "mode": "autonomous"},
            )
        return Decision(
            next_state=CandidateState.HIRE_RECOMMENDED,
            reasoning=f"Composite {composite:.2f} ≥ {HIRE_THRESHOLD} — hire recommended, awaiting founder confirmation.",
            requires_founder_approval=True,
            fsm_context={"composite": composite, "mode": "recommend"},
        )

    if composite >= RESUBMIT_THRESHOLD:
        return Decision(
            next_state=CandidateState.AWAITING_RESUBMISSION,
            reasoning=(
                f"Composite {composite:.2f} in [{RESUBMIT_THRESHOLD}, {HIRE_THRESHOLD}) — "
                "strong enough to resubmit, not yet at hire bar."
            ),
            requires_founder_approval=False,
            fsm_context={"composite": composite},
        )

    # composite < RESUBMIT_THRESHOLD
    if rounds_completed >= MAX_RESUBMISSION_ROUNDS:
        return Decision(
            next_state=CandidateState.WARM_HOLD,
            reasoning=(
                f"Composite {composite:.2f} < {RESUBMIT_THRESHOLD} after {rounds_completed} rounds — "
                "no improvement path. Moving to warm hold."
            ),
            requires_founder_approval=False,
            fsm_context={"composite": composite, "rounds": rounds_completed},
        )

    # First round, low composite — one more chance
    return Decision(
        next_state=CandidateState.AWAITING_RESUBMISSION,
        reasoning=(
            f"Composite {composite:.2f} < {RESUBMIT_THRESHOLD} but only round {rounds_completed} — "
            "one resubmission opportunity granted."
        ),
        requires_founder_approval=False,
        fsm_context={"composite": composite, "rounds": rounds_completed},
    )
