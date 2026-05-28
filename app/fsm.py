import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Tuple
from dataclasses import dataclass

log = logging.getLogger(__name__)

class CandidateState(str, Enum):
    """Finite State Machine states for candidate lifecycle."""
    NEW = "NEW"
    ENGAGED = "ENGAGED"
    GATHERING_BACKGROUND = "GATHERING_BACKGROUND"
    JD_SHARED = "JD_SHARED"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    AWAITING_SUBMISSION = "AWAITING_SUBMISSION"
    UNDER_EVALUATION = "UNDER_EVALUATION"
    PENDING_CEO_REVIEW = "PENDING_CEO_REVIEW"
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
    predicate_fn: Callable[[Dict[str, Any]], bool]

class FSMEngine:
    """
    Finite state machine engine for candidate lifecycle.
    
    Single source of truth for allowed transitions. No conditional logic
    in upstream code; all state changes route through transition().
    
    Every transition is logged immutably with timestamp, actor, predicate,
    and context.
    """
    
    def __init__(self, db_session: Any = None) -> None:
        """
        Args:
            db_session: SQLAlchemy async session for transaction management.
                        If None, transitions are logged in-memory (dev/test only).
        """
        self.db = db_session
        self.transition_table = self._build_transition_table()
        self.transition_log: List[Dict[str, Any]] = []
    
    @staticmethod
    def _build_transition_table() -> Dict[Tuple[CandidateState, CandidateState], FSMTransition]:
        """
        Build the canonical transition table.
        
        Every allowed state→state transition is defined here.
        Any transition not in this table is rejected and logged.
        """
        
        predicates: Dict[str, Callable[[Dict[str, Any]], bool]] = {
            "intake_complete": lambda ctx: ctx.get("intake_complete", False),
            "intent_interested_or_scheduling": lambda ctx: ctx.get("intent") in ["INTERESTED", "SCHEDULING"],
            "task_generated": lambda ctx: bool(ctx.get("task_id")),
            "intent_declined": lambda ctx: ctx.get("intent") == "DECLINE",
            "task_brief_sent": lambda ctx: ctx.get("task_brief_sent", False),
            "repo_provisioned": lambda ctx: bool(ctx.get("repo_url")),
            "submission_sha_pinned": lambda ctx: bool(ctx.get("submission_sha")),
            "evaluation_complete": lambda ctx: ctx.get("evaluation_record_id") is not None,
            "ceo_reviewed": lambda ctx: ctx.get("ceo_action") in ("accept", "reject", "resubmit"),
            # Resubmit: score below hire bar AND not yet at warm-hold threshold
            "needs_resubmission": lambda ctx: (
                ctx.get("composite", 0) < 8.5
                and not (ctx.get("composite", 0) < 7.0 and ctx.get("rounds", 0) >= 2)
            ),
            "composite_below_7_no_improvement": lambda ctx: ctx.get("composite", 0) < 7.0 and ctx.get("rounds", 0) >= 2,
            "composite_above_8_5_recommend": lambda ctx: ctx.get("composite", 0) >= 8.5 and ctx.get("mode") == "recommend",
            "composite_above_8_5_autonomous": lambda ctx: ctx.get("composite", 0) >= 8.5 and ctx.get("mode") == "autonomous",
            "founder_confirmed_hire": lambda ctx: ctx.get("founder_confirmed", False),
            "founder_sent_offer": lambda ctx: ctx.get("offer_sent", False),
            "resubmission_sha_pinned": lambda ctx: bool(ctx.get("resubmission_sha")),
        }
        
        transitions = [
            FSMTransition(CandidateState.NEW, CandidateState.ENGAGED, "intake_complete", predicates["intake_complete"]),
            FSMTransition(CandidateState.ENGAGED, CandidateState.GATHERING_BACKGROUND, "intent_interested",
                         lambda ctx: ctx.get("intent") == "INTERESTED"),
            FSMTransition(CandidateState.GATHERING_BACKGROUND, CandidateState.JD_SHARED, "profile_complete",
                         lambda ctx: ctx.get("profile_complete", False)),
            FSMTransition(CandidateState.GATHERING_BACKGROUND, CandidateState.WITHDRAWN, "intent_declined", predicates["intent_declined"]),
            FSMTransition(CandidateState.JD_SHARED, CandidateState.TASK_ASSIGNED, "intent_interested_and_task_generated",
                         lambda ctx: predicates["intent_interested_or_scheduling"](ctx) and predicates["task_generated"](ctx)),
            FSMTransition(CandidateState.JD_SHARED, CandidateState.WITHDRAWN, "intent_declined", predicates["intent_declined"]),
            FSMTransition(CandidateState.ENGAGED, CandidateState.TASK_ASSIGNED, "intent_interested_and_task_generated",
                         lambda ctx: predicates["intent_interested_or_scheduling"](ctx) and predicates["task_generated"](ctx)),
            FSMTransition(CandidateState.ENGAGED, CandidateState.WITHDRAWN, "intent_declined", predicates["intent_declined"]),
            FSMTransition(CandidateState.TASK_ASSIGNED, CandidateState.AWAITING_SUBMISSION, "task_brief_sent",
                         predicates["task_brief_sent"]),
            FSMTransition(CandidateState.AWAITING_SUBMISSION, CandidateState.UNDER_EVALUATION, "submission_sha_pinned", predicates["submission_sha_pinned"]),
            FSMTransition(CandidateState.UNDER_EVALUATION, CandidateState.PENDING_CEO_REVIEW, "evaluation_complete", predicates["evaluation_complete"]),
            FSMTransition(CandidateState.PENDING_CEO_REVIEW, CandidateState.FEEDBACK_SENT, "ceo_reviewed", predicates["ceo_reviewed"]),
            FSMTransition(CandidateState.PENDING_CEO_REVIEW, CandidateState.WARM_HOLD, "ceo_reviewed", predicates["ceo_reviewed"]),
            FSMTransition(CandidateState.PENDING_CEO_REVIEW, CandidateState.AWAITING_RESUBMISSION, "ceo_reviewed", predicates["ceo_reviewed"]),
            FSMTransition(CandidateState.FEEDBACK_SENT, CandidateState.AWAITING_RESUBMISSION, "needs_resubmission", predicates["needs_resubmission"]),
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
        context: Dict[str, Any],
        actor: str = "system",
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
        from app.database import AsyncSessionLocal
        from app.orm_models import CandidateRow
        async with AsyncSessionLocal() as session:
            row = await session.get(CandidateRow, candidate_id)
            if row is None:
                return CandidateState.NEW
            return CandidateState(row.state)

    async def force_set_state(
        self,
        candidate_id: str,
        target_state: CandidateState,
        actor: str = "founder",
        reason: str = "",
    ) -> CandidateState:
        """
        Founder override — write state directly, bypassing transition table and predicates.
        Logs the action and returns the previous state.
        """
        previous = await self._get_current_state(candidate_id)
        await self._set_state(candidate_id, target_state)
        log.info(
            "FSM force-override %s: %s → %s (actor=%s reason=%r)",
            candidate_id, previous, target_state, actor, reason,
        )
        return previous

    async def _set_state(self, candidate_id: str, state: CandidateState) -> None:
        from datetime import datetime as _dt
        from sqlalchemy import update as _update
        from app.database import AsyncSessionLocal
        from app.orm_models import CandidateRow
        async with AsyncSessionLocal() as session:
            await session.execute(
                _update(CandidateRow)
                .where(CandidateRow.id == candidate_id)
                .values(state=state.value, updated_at=_dt.utcnow())
            )
            await session.commit()
    
    def _log_rejected_transition(self, candidate_id: str, from_state: CandidateState, to_state: CandidateState, actor: str, reason: str) -> None:
        self.transition_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "candidate_id": candidate_id,
            "from_state": from_state.value,
            "to_state": to_state.value,
            "actor": actor,
            "status": "REJECTED",
            "reason": reason,
        })
        log.warning("FSM rejected %s: %s → %s (%s)", candidate_id, from_state, to_state, reason)
        self._persist_transition(candidate_id, from_state, to_state, reason, actor, "REJECTED")

    def _log_transition(self, candidate_id: str, from_state: CandidateState, to_state: CandidateState, actor: str, predicate: str, context: Dict[str, Any]) -> None:
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
        log.info("FSM transition %s: %s → %s (predicate: %s)", candidate_id, from_state, to_state, predicate)
        self._persist_transition(candidate_id, from_state, to_state, predicate, actor, "SUCCESS")

    @staticmethod
    def _persist_transition(
        candidate_id: str,
        from_state: CandidateState,
        to_state: CandidateState,
        predicate: str,
        actor: str,
        status: str,
    ) -> None:
        """Fire-and-forget write to the transitions table."""
        import asyncio
        async def _write() -> None:
            try:
                from app.database import AsyncSessionLocal
                from app.orm_models import TransitionRow
                async with AsyncSessionLocal() as session:
                    session.add(TransitionRow(
                        candidate_id=candidate_id,
                        from_state=from_state.value,
                        to_state=to_state.value,
                        predicate=predicate,
                        actor=actor,
                        status=status,
                    ))
                    await session.commit()
            except Exception:
                pass  # never block FSM on DB write
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_write())
            else:
                loop.run_until_complete(_write())
        except Exception:
            pass
