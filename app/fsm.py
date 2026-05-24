import json
from datetime import datetime
from enum import Enum
from typing import Dict, Tuple
from dataclasses import dataclass

class CandidateState(str, Enum):
    """Finite State Machine states for candidate lifecycle."""
    NEW = "NEW"
    ENGAGED = "ENGAGED"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    AWAITING_SUBMISSION = "AWAITING_SUBMISSION"
    UNDER_EVALUATION = "UNDER_EVALUATION"
    FEEDBACK_SENT = "FEEDBACK_SENT"
    AWAITING_RESUBMISSION = "AWAITING_RESUBMISSION"
    HIRE_RECOMMENDED = "HIRE_RECOMMENDED"
    OFFER_DRAFTED = "OFFER_DRAFTED"
    HIRED = "HIRED"
    WARM_HOLD = "WARM_HOLD"
    WITHDRAWN = "WITHDRAWN"

@dataclass
class FSMTransition:
    """Represents an allowed state transition with predicate."""
    from_state: CandidateState
    to_state: CandidateState
    predicate_name: str
    predicate_fn: callable  # (context: dict) -> bool

class FSMEngine:
    """
    Finite state machine engine for candidate lifecycle.
    
    Single source of truth for allowed transitions. No conditional logic
    in upstream code; all state changes route through transition().
    
    Every transition is logged immutably with timestamp, actor, predicate,
    and context.
    """
    
    def __init__(self, db_session=None):
        """
        Args:
            db_session: SQLAlchemy async session for transaction management.
                        If None, transitions are logged in-memory (dev/test only).
        """
        self.db = db_session
        self.transition_table = self._build_transition_table()
        self.transition_log = []  # In-memory log (replace with DB in production)
    
    @staticmethod
    def _build_transition_table() -> Dict[Tuple[CandidateState, CandidateState], FSMTransition]:
        """
        Build the canonical transition table.
        
        Every allowed state→state transition is defined here.
        Any transition not in this table is rejected and logged.
        """
        
        # Predicates: pure functions that determine if transition is allowed
        predicates = {
            "intake_complete": lambda ctx: ctx.get("intake_complete", False),
            "intent_interested_or_scheduling": lambda ctx: ctx.get("intent") in ["INTERESTED", "SCHEDULING"],
            "task_generated": lambda ctx: bool(ctx.get("task_id")),
            "intent_declined": lambda ctx: ctx.get("intent") == "DECLINE",
            "task_brief_sent": lambda ctx: ctx.get("task_brief_sent", False),
            "repo_provisioned": lambda ctx: bool(ctx.get("repo_url")),
            "submission_sha_pinned": lambda ctx: bool(ctx.get("submission_sha")),
            "evaluation_complete": lambda ctx: ctx.get("evaluation_record_id") is not None,
            "composite_7_to_8_4": lambda ctx: 7.0 <= ctx.get("composite", 0) < 8.5,
            "composite_below_7_no_improvement": lambda ctx: ctx.get("composite", 0) < 7.0 and ctx.get("rounds", 0) >= 2,
            "composite_above_8_5_recommend": lambda ctx: ctx.get("composite", 0) >= 8.5 and ctx.get("mode") == "recommend",
            "composite_above_8_5_autonomous": lambda ctx: ctx.get("composite", 0) >= 8.5 and ctx.get("mode") == "autonomous",
            "founder_confirmed_hire": lambda ctx: ctx.get("founder_confirmed", False),
            "founder_sent_offer": lambda ctx: ctx.get("offer_sent", False),
            "resubmission_sha_pinned": lambda ctx: bool(ctx.get("resubmission_sha")),
        }
        
        transitions = [
            FSMTransition(CandidateState.NEW, CandidateState.ENGAGED, "intake_complete", predicates["intake_complete"]),
            FSMTransition(CandidateState.ENGAGED, CandidateState.TASK_ASSIGNED, "intent_interested_and_task_generated",
                         lambda ctx: predicates["intent_interested_or_scheduling"](ctx) and predicates["task_generated"](ctx)),
            FSMTransition(CandidateState.ENGAGED, CandidateState.WITHDRAWN, "intent_declined", predicates["intent_declined"]),
            FSMTransition(CandidateState.TASK_ASSIGNED, CandidateState.AWAITING_SUBMISSION, "task_brief_and_repo_ready",
                         lambda ctx: predicates["task_brief_sent"](ctx) and predicates["repo_provisioned"](ctx)),
            FSMTransition(CandidateState.AWAITING_SUBMISSION, CandidateState.UNDER_EVALUATION, "submission_sha_pinned", predicates["submission_sha_pinned"]),
            FSMTransition(CandidateState.UNDER_EVALUATION, CandidateState.FEEDBACK_SENT, "evaluation_complete", predicates["evaluation_complete"]),
            FSMTransition(CandidateState.FEEDBACK_SENT, CandidateState.AWAITING_RESUBMISSION, "composite_7_to_8_4", predicates["composite_7_to_8_4"]),
            FSMTransition(CandidateState.FEEDBACK_SENT, CandidateState.WARM_HOLD, "composite_below_7_no_improvement", predicates["composite_below_7_no_improvement"]),
            FSMTransition(CandidateState.FEEDBACK_SENT, CandidateState.HIRE_RECOMMENDED, "composite_above_8_5_recommend", predicates["composite_above_8_5_recommend"]),
            FSMTransition(CandidateState.FEEDBACK_SENT, CandidateState.HIRED, "composite_above_8_5_autonomous", predicates["composite_above_8_5_autonomous"]),
            FSMTransition(CandidateState.AWAITING_RESUBMISSION, CandidateState.UNDER_EVALUATION, "resubmission_sha_pinned", predicates["resubmission_sha_pinned"]),
            FSMTransition(CandidateState.HIRE_RECOMMENDED, CandidateState.OFFER_DRAFTED, "founder_confirmed_hire", predicates["founder_confirmed_hire"]),
            FSMTransition(CandidateState.OFFER_DRAFTED, CandidateState.HIRED, "founder_sent_offer", predicates["founder_sent_offer"]),
            # Future: WARM_HOLD → ENGAGED for re-engagement
        ]
        
        # Build lookup table: (from_state, to_state) → FSMTransition
        table = {}
        for transition in transitions:
            key = (transition.from_state, transition.to_state)
            table[key] = transition
        
        return table
    
    async def transition(
        self,
        candidate_id: str,
        target_state: CandidateState,
        context: dict,
        actor: str = "system"
    ) -> bool:
        """
        Attempt a state transition for a candidate.
        """
        current_state = await self._get_current_state(candidate_id)
        
        key = (current_state, target_state)
        if key not in self.transition_table:
            self._log_rejected_transition(candidate_id, current_state, target_state, actor, "not_in_transition_table")
            return False
        
        transition_spec = self.transition_table[key]
        
        if not transition_spec.predicate_fn(context):
            self._log_rejected_transition(candidate_id, current_state, target_state, actor, transition_spec.predicate_name)
            return False
        
        try:
            await self._set_state(candidate_id, target_state)
            self._log_transition(candidate_id, current_state, target_state, actor, transition_spec.predicate_name, context)
            return True
        except Exception as e:
            self._log_rejected_transition(candidate_id, current_state, target_state, actor, f"db_error: {e}")
            return False
    
    async def _get_current_state(self, candidate_id: str) -> CandidateState:
        """Stub: Replace with actual DB query."""
        return CandidateState.NEW
    
    async def _set_state(self, candidate_id: str, state: CandidateState) -> None:
        """Stub: Replace with actual DB update."""
        pass
    
    def _log_rejected_transition(self, candidate_id: str, from_state: CandidateState, to_state: CandidateState, actor: str, reason: str) -> None:
        """Log a rejected transition."""
        self.transition_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "candidate_id": candidate_id,
            "from_state": from_state.value,
            "to_state": to_state.value,
            "actor": actor,
            "status": "REJECTED",
            "reason": reason,
        })
        print(f"[REJECTED] {candidate_id}: {from_state} → {to_state} ({reason})")
    
    def _log_transition(self, candidate_id: str, from_state: CandidateState, to_state: CandidateState, actor: str, predicate: str, context: dict) -> None:
        """Log a successful transition."""
        self.transition_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "candidate_id": candidate_id,
            "from_state": from_state.value,
            "to_state": to_state.value,
            "actor": actor,
            "predicate": predicate,
            "status": "SUCCESS",
            "context": context,
        })
        print(f"[TRANSITION] {candidate_id}: {from_state} → {to_state} (predicate: {predicate})")
