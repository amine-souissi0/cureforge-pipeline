from __future__ import annotations

import html
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from agents.email_agent import send_email
from models.database import OutreachRecord, ReplyStatus, SessionLocal, init_db

logger = logging.getLogger(__name__)

DAY_3_SUBJECT_PREFIX = "Re: "
DAY_3_BODY = """Hi {name},

I wanted to gently bump this in case it got buried.

Would it be useful to schedule a short demo of CureForge AI and the autonomous longevity research federation?

Best,
Oleg"""

DAY_7_BODY = """Hi {name},

One last quick follow-up from me.

If CureForge AI is not a fit for your current focus, no worries. If it is relevant, I would welcome a short conversation.

Best,
Oleg"""


@dataclass
class FollowUpResult:
    due: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0


def due_follow_up_stage(record: OutreachRecord, now: datetime | None = None) -> int | None:
    now = now or datetime.utcnow()
    if not record.sent_at or record.reply_status != ReplyStatus.pending:
        return None
    if record.follow_up_stage == 0 and record.sent_at <= now - timedelta(days=3):
        return 1
    if record.follow_up_stage == 1 and record.sent_at <= now - timedelta(days=7):
        return 2
    return None


def build_follow_up(record: OutreachRecord, stage: int) -> tuple[str, str]:
    subject = record.drafted_subject or "CureForge AI"
    if not subject.lower().startswith("re:"):
        subject = f"{DAY_3_SUBJECT_PREFIX}{subject}"

    name = record.name or record.firm or "there"
    body = DAY_3_BODY if stage == 1 else DAY_7_BODY
    html_body = "\n".join(
        f"<p>{html.escape(paragraph.format(name=name))}</p>"
        for paragraph in body.split("\n\n")
    )
    return subject, html_body


def run_due_follow_ups(*, limit: int | None = None, dry_run: bool = False) -> FollowUpResult:
    init_db()
    now = datetime.utcnow()
    result = FollowUpResult()

    db = SessionLocal()
    try:
        query = (
            db.query(OutreachRecord)
            .filter(OutreachRecord.sent_at.isnot(None))
            .filter(OutreachRecord.reply_status == ReplyStatus.pending)
            .order_by(OutreachRecord.sent_at.asc())
        )
        records = query.limit(limit).all() if limit else query.all()

        for record in records:
            stage = due_follow_up_stage(record, now)
            if stage is None:
                result.skipped += 1
                continue

            result.due += 1
            subject, html_body = build_follow_up(record, stage)
            if dry_run:
                logger.info("[DRY RUN] Would send day-%s follow-up to %s", 3 if stage == 1 else 7, record.email)
                result.sent += 1
                continue

            try:
                message_id = send_email(record.email, subject, html_body)
            except Exception as exc:
                logger.error("Follow-up failed for %s: %s", record.email, exc)
                result.failed += 1
                continue

            message_ids = json.loads(record.follow_up_message_ids or "[]")
            message_ids.append({"stage": stage, "message_id": message_id, "sent_at": now.isoformat()})
            record.follow_up_stage = stage
            record.follow_up_message_ids = json.dumps(message_ids)
            record.last_follow_up_at = now
            record.next_follow_up_at = record.sent_at + timedelta(days=7) if stage == 1 else None
            record.pipeline_status = "followed_up" if stage == 1 else "follow_up_complete"
            db.commit()
            result.sent += 1

        return result
    finally:
        db.close()
