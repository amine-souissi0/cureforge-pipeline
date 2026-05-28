"""
Webhook processor: turns a parsed inbound Gmail message into pipeline actions.

Separated from the Celery task so the logic is unit-testable without a broker.
"""
from typing import Optional

from app.fsm import CandidateState, FSMEngine
from app.models import CandidateModel
from app.schemas import AuditLog, Message, ReplyClassifierOutput


async def process_inbound_message(message: Message) -> str:
    """
    Full pipeline for one inbound Gmail message.

    §5.1: trigger is "founder adds a candidate OR forwards the candidate's first email."
    When an email arrives from an unknown address we auto-intake the candidate (NEW state)
    and queue an invite draft — their name appears in the UI immediately.

    Returns a short result string for the Celery task log.
    """
    from app.agents.reply_classifier import ReplyClassifierAgent, route_classified_email
    from app.services.candidate_store import CandidateStore
    from app.config import PIPELINE_EMAIL

    # Skip messages sent BY the pipeline itself (appear in history for same-thread events)
    if message.sender_email == PIPELINE_EMAIL:
        return f"skip_own:{message.message_id}"

    candidate = await CandidateStore.get_by_email(message.sender_email)
    if candidate is None:
        await AuditLog.append("cold_inbound_rejected", {
            "sender_email": message.sender_email,
            "gmail_message_id": message.message_id,
        })
        return f"cold_inbound_rejected:{message.sender_email}"

    await AuditLog.append("webhook_candidate_matched", {
        "candidate_id": candidate.id,
        "sender_email": message.sender_email,
        "state": candidate.state.value,
        "gmail_message_id": message.message_id,
    })

    # §11 messages table — log every inbound email
    from app.services.message_store import MessageStore
    await MessageStore.log_inbound(
        candidate_id=candidate.id,
        body=message.body,
        subject=message.subject,
        gmail_id=message.message_id,
    )

    output = await ReplyClassifierAgent.classify_email(
        email_body=message.body,
        candidate_context=candidate.name,
        candidate_state=candidate.state.value,
    )

    routing = route_classified_email(output, candidate.id)

    await AuditLog.append("email_classified", {
        "candidate_id": candidate.id,
        "intent": output.intent,
        "confidence": output.confidence,
        "routing": routing,
        "summary": output.summary,
        "gmail_message_id": message.message_id,
    })

    await _execute_routing(routing, candidate, message, output)
    return f"{candidate.id}:{output.intent}→{routing}"


async def _execute_routing(
    routing: str,
    candidate: CandidateModel,
    message: Message,
    output: ReplyClassifierOutput,
) -> None:
    if routing == "fsm_withdrawn":
        await _handle_decline(candidate)
        return

    if routing == "background_intake":
        await _handle_background_submitted(candidate, message)
        return

    if routing.startswith("jd_confirmed:"):
        jd_title = routing.split(":", 1)[1]
        await _handle_jd_confirmed(candidate, jd_title)
        return

    if routing == "jd_declined":
        await _handle_decline(candidate)
        return

    if routing.startswith("submission_intake:"):
        submission_url = routing.split(":", 1)[1]
        await _handle_submission(candidate, message, submission_url)
        return

    if routing == "request_submission_url":
        await _handle_request_submission_url(candidate, message)
        return

    if routing.startswith("template_responder:"):
        intent = routing.split(":", 1)[1]
        await _handle_template_response(candidate, message, intent)
        return

    # human_review — flag for founder, no automated action
    await AuditLog.append("human_review_flagged", {
        "candidate_id": candidate.id,
        "intent": output.intent,
        "confidence": output.confidence,
        "summary": output.summary,
        "gmail_message_id": message.message_id,
        "routing": routing,
    })


async def _handle_decline(candidate: CandidateModel) -> None:
    from app.services.candidate_store import CandidateStore

    fsm = FSMEngine()
    transitioned = await fsm.transition(
        candidate_id=candidate.id,
        target_state=CandidateState.WITHDRAWN,
        context={"intent": "DECLINE"},
        actor="webhook_processor",
    )
    if transitioned:
        await CandidateStore.update_state(candidate.id, CandidateState.WITHDRAWN)

    await AuditLog.append("candidate_withdrawn", {
        "candidate_id": candidate.id,
        "reason": "DECLINE_intent",
        "fsm_transitioned": transitioned,
    })


async def _handle_submission(
    candidate: CandidateModel,
    message: Message,
    submission_url: str,
) -> None:
    from app.services.task_store import TaskStore

    task = await TaskStore.get_by_candidate(candidate.id)
    if task:
        await TaskStore.update_repo_url(task.id, submission_url)

    await AuditLog.append("submission_received", {
        "candidate_id": candidate.id,
        "submission_url": submission_url,
        "task_id": task.id if task else None,
        "candidate_state": candidate.state.value,
        "gmail_message_id": message.message_id,
    })

    # No acknowledgment here — the evaluation feedback is the response to a submission.

    # Auto-trigger evaluation whenever a submission arrives and we have a task ready.
    # Include TASK_ASSIGNED: brief was sent but the AWAITING_SUBMISSION transition may not
    # have fired yet (e.g. brief was drafted, not auto-sent).
    submission_states = {CandidateState.AWAITING_SUBMISSION, CandidateState.AWAITING_RESUBMISSION, CandidateState.TASK_ASSIGNED}
    if candidate.state in submission_states and task:
        from app.api.candidates import run_submission_evaluation
        run_submission_evaluation.delay(candidate.id, submission_url)
        await AuditLog.append("submission_evaluation_enqueued", {
            "candidate_id": candidate.id,
            "submission_url": submission_url,
            "task_id": task.id,
            "state": candidate.state.value,
        })


async def _handle_request_submission_url(
    candidate: CandidateModel,
    message: Message,
) -> None:
    """Auto-send a polite URL request when candidate signals submission but omits the link."""
    await AuditLog.append("submission_url_missing", {
        "candidate_id": candidate.id,
        "gmail_message_id": message.message_id,
    })
    await _queue_template(
        candidate=candidate,
        template_id="request-submission-url",
        original_subject=message.subject,
    )


async def _handle_background_submitted(
    candidate: CandidateModel,
    message: Message,
) -> None:
    """
    Candidate responded to the profile questionnaire.
    1. Parse resume → structured profile
    2. Validate sufficiency — if insufficient, ask for missing details
    3. Run JD matching → share top roles
    4. Transition to JD_SHARED
    """
    from app.agents.resume_parser import ResumeParserAgent
    from app.agents.jd_matcher import JDMatcherAgent
    from app.services.candidate_store import CandidateStore
    from config.jobs import JOBS

    # --- Step 1: Parse ---
    profile = await ResumeParserAgent.parse(
        email_body=message.body,
        candidate_role=candidate.role,
    )

    await AuditLog.append("resume_parsed", {
        "candidate_id": candidate.id,
        "is_sufficient": profile.get("is_sufficient"),
        "inferred_level": profile.get("inferred_level"),
        "skills": profile.get("skills", []),
        "location": profile.get("location"),
        "notice_period": profile.get("notice_period"),
        "missing_fields": profile.get("missing_fields", []),
    })

    # --- Step 2: Validate sufficiency ---
    if not profile.get("is_sufficient"):
        missing = profile.get("missing_fields", ["skills", "experience"])
        missing_details = "\n".join(f"- {f.replace('_', ' ').title()}" for f in missing)
        await _queue_template(
            candidate=candidate,
            template_id="profile-incomplete",
            original_subject=message.subject,
            extra_context={"missing_details": missing_details},
        )
        await AuditLog.append("profile_incomplete_requested", {
            "candidate_id": candidate.id,
            "missing_fields": missing,
        })
        return  # stay in GATHERING_BACKGROUND

    # --- Step 3: Store profile ---
    inferred_level = profile.get("inferred_level", candidate.level)
    summary_parts = [profile.get("summary", "")]
    if profile.get("skills"):
        summary_parts.append(f"Skills: {', '.join(profile['skills'])}")
    if profile.get("location"):
        summary_parts.append(f"Location: {profile['location']}")
    if profile.get("notice_period"):
        summary_parts.append(f"Notice: {profile['notice_period']}")
    background_notes = "\n".join(p for p in summary_parts if p)

    await CandidateStore.update_profile(
        candidate_id=candidate.id,
        candidate_profile=profile,
        background_notes=background_notes,
        level=inferred_level,
        location=profile.get("location"),
        notice_period=profile.get("notice_period"),
        preferred_roles=profile.get("preferred_roles"),
    )

    # --- Step 4: JD matching ---
    match_result = await JDMatcherAgent.match(profile)
    matches = match_result.get("matches", [])

    await AuditLog.append("jd_matched", {
        "candidate_id": candidate.id,
        "top_jd_id": match_result.get("top_jd_id"),
        "match_scores": {m["jd_id"]: m["score"] for m in matches},
    })

    # --- Step 5: Build JD list and share ---
    jd_lines = []
    for m in matches:
        jd = JOBS.get(m["jd_id"])
        if not jd:
            continue
        jd_lines.append(
            f"**{jd.title}** ({jd.team} · {jd.location})\n"
            f"{jd.description}"
        )

    jd_list = "\n\n---\n\n".join(jd_lines) if jd_lines else "We'll follow up with relevant openings shortly."

    await _queue_template(
        candidate=candidate,
        template_id="jd-sharing",
        original_subject=message.subject,
        extra_context={"jd_list": jd_list},
    )

    # --- Step 6: FSM → JD_SHARED ---
    fsm = FSMEngine()
    transitioned = await fsm.transition(
        candidate_id=candidate.id,
        target_state=CandidateState.JD_SHARED,
        context={"profile_complete": True},
        actor="webhook_processor",
    )
    if transitioned:
        from app.services.candidate_store import CandidateStore as _CS
        await _CS.update_state(candidate.id, CandidateState.JD_SHARED)

    await AuditLog.append("jd_shared", {
        "candidate_id": candidate.id,
        "jd_count": len(jd_lines),
        "fsm_transitioned": transitioned,
    })


async def _handle_jd_confirmed(
    candidate: CandidateModel,
    jd_title: str,
) -> None:
    """
    Candidate confirmed interest in a specific JD.
    Resolve which JD they meant, store it, trigger task generation.
    """
    from app.services.candidate_store import CandidateStore
    from app.api.candidates import generate_task_for_candidate
    from config.jobs import JOBS

    # Resolve JD by title match (case-insensitive partial)
    confirmed_jd = None
    jd_title_lower = jd_title.lower()
    for jd in JOBS.values():
        if jd_title_lower and jd_title_lower in jd.title.lower():
            confirmed_jd = jd
            break
    # Fallback: use top match from stored profile
    if confirmed_jd is None and candidate.candidate_profile:
        from app.agents.jd_matcher import JDMatcherAgent
        match_result = await JDMatcherAgent.match(candidate.candidate_profile)
        top_id = match_result.get("top_jd_id")
        confirmed_jd = JOBS.get(top_id) if top_id else None
    # Last resort: first job
    if confirmed_jd is None:
        confirmed_jd = next(iter(JOBS.values()), None)

    if confirmed_jd is None:
        await AuditLog.append("jd_confirmed_no_match", {
            "candidate_id": candidate.id,
            "jd_title": jd_title,
        })
        return

    await CandidateStore.update_confirmed_jd(candidate.id, confirmed_jd.id)

    await AuditLog.append("jd_confirmed", {
        "candidate_id": candidate.id,
        "confirmed_jd_id": confirmed_jd.id,
        "confirmed_jd_title": confirmed_jd.title,
        "jd_title_from_message": jd_title,
    })

    # Trigger task generation with JD context
    generate_task_for_candidate.delay(
        candidate.id,
        confirmed_jd.title,
        candidate.level,
        confirmed_jd.task_corpus_pattern or "",
    )

    await AuditLog.append("task_generation_enqueued", {
        "candidate_id": candidate.id,
        "trigger": "jd_confirmed",
        "confirmed_jd_id": confirmed_jd.id,
        "corpus_pattern": confirmed_jd.task_corpus_pattern,
    })


async def _handle_template_response(
    candidate: CandidateModel,
    message: Message,
    intent: str,
) -> None:
    template_id = _intent_to_template(intent)
    if template_id is None:
        await AuditLog.append("no_template_for_intent", {
            "candidate_id": candidate.id,
            "intent": intent,
        })
        return

    # For QUESTION intent, pass the question text so the LLM can generate a real answer
    extra: dict = {}
    if intent == "QUESTION":
        extra = {"question_text": message.body, "original_subject": message.subject}

    await _queue_template(
        candidate=candidate,
        template_id=template_id,
        original_subject=message.subject,
        extra_context=extra,
    )

    # INTERESTED → ask for background first, then generate task after response
    if intent == "INTERESTED":
        fsm = FSMEngine()
        transitioned = await fsm.transition(
            candidate_id=candidate.id,
            target_state=CandidateState.GATHERING_BACKGROUND,
            context={"intent": "INTERESTED"},
            actor="webhook_processor",
        )
        if transitioned:
            from app.services.candidate_store import CandidateStore
            await CandidateStore.update_state(candidate.id, CandidateState.GATHERING_BACKGROUND)
        await AuditLog.append("background_gathering_started", {
            "candidate_id": candidate.id,
            "fsm_transitioned": transitioned,
        })


def _intent_to_template(intent: str) -> Optional[str]:
    # INTERESTED: send background questionnaire (task generation waits for response).
    # SCHEDULING: candidates proposing calls get routed to human review (no template).
    # QUESTION: generate a real answer.
    return {
        "INTERESTED": "background-request",
        "QUESTION": "answer-common-question",
    }.get(intent)


async def _auto_intake_candidate(message: Message) -> Optional[CandidateModel]:
    """
    Create a NEW-state candidate from an inbound email by an unknown sender.

    Returns the created (or already-existing) CandidateModel, or None on failure.
    """
    from fastapi import HTTPException

    from app.services.candidate_store import CandidateStore

    candidate = CandidateModel(
        name=message.sender_name,
        email=message.sender_email,
        source="email_forwarded",
    )
    try:
        await CandidateStore.add(candidate)
    except HTTPException as exc:
        if exc.status_code == 409:
            # Race condition: another worker already created this candidate.
            candidate = await CandidateStore.get_by_email(message.sender_email)
            if candidate is None:
                return None
        else:
            return None

    await AuditLog.append("candidate_auto_intaked", {
        "candidate_id": candidate.id,
        "sender_email": message.sender_email,
        "sender_name": message.sender_name,
        "gmail_message_id": message.message_id,
    })

    # NEW → ENGAGED so all downstream FSM transitions (ENGAGED → TASK_ASSIGNED etc.) work.
    from app.fsm import FSMEngine, CandidateState as _CS
    from app.services.candidate_store import CandidateStore as _CS2
    fsm = FSMEngine()
    transitioned = await fsm.transition(
        candidate_id=candidate.id,
        target_state=_CS.ENGAGED,
        context={"intake_complete": True},
        actor="auto_intake",
    )
    if transitioned:
        await _CS2.update_state(candidate.id, _CS.ENGAGED)
        candidate = candidate.model_copy(update={"state": _CS.ENGAGED})

    await _queue_template(
        candidate=candidate,
        template_id="acknowledgment",
        original_subject=message.subject,
    )

    return candidate


async def _queue_template(
    candidate: CandidateModel,
    template_id: str,
    original_subject: str = "",
    extra_context: dict | None = None,
) -> None:
    from app.agents.template_responder import TemplateResponderAgent
    from app.services.approval_queue import ApprovalQueue, DraftEmail
    from app.services.send_policy import SendMode, get_send_mode

    try:
        result = await TemplateResponderAgent.render(
            template_id=template_id,
            candidate_context={
                "candidate_name": candidate.name,
                "sender_name": "LongevityInTime Team",
                "original_subject": original_subject,
            },
            extra_context=extra_context,
        )
    except Exception as e:
        await AuditLog.append("template_render_failed", {
            "candidate_id": candidate.id,
            "template_id": template_id,
            "error": str(e),
        })
        return

    send_mode = get_send_mode(candidate.id, template_id)

    if send_mode == SendMode.AUTO:
        from app.services.gmail_service import GmailService
        from app.services.message_store import MessageStore
        svc = GmailService()
        try:
            gmail_id = await svc.send_email(
                to=candidate.email,
                subject=result.subject,
                body=result.body,
            )
            await AuditLog.append("template_auto_sent", {
                "candidate_id": candidate.id,
                "template_id": template_id,
                "gmail_id": gmail_id,
            })
            await MessageStore.log_outbound(
                candidate_id=candidate.id,
                body=result.body,
                subject=result.subject,
                template_id=template_id,
                gmail_id=gmail_id,
            )
        except Exception as e:
            await AuditLog.append("template_send_failed", {
                "candidate_id": candidate.id,
                "template_id": template_id,
                "error": str(e),
            })
    else:
        draft = DraftEmail(
            candidate_id=candidate.id,
            template_id=template_id,
            subject=result.subject,
            body=result.body,
            to_email=candidate.email,
        )
        draft_id = await ApprovalQueue.add(draft)
        await AuditLog.append("template_draft_queued", {
            "candidate_id": candidate.id,
            "template_id": template_id,
            "draft_id": draft_id,
        })
