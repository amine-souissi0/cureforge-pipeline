from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from agents.email_agent import send_and_record
from agents.email_enrichment import find_email_for_org
from models.database import OutreachRecord, SessionLocal, init_db

logger = logging.getLogger(__name__)


@dataclass
class BridgeResult:
    queued: int = 0
    skipped: int = 0
    sent: int = 0
    failed: int = 0


def text_to_html(body: str) -> str:
    paragraphs = [p.strip() for p in (body or "").split("\n\n") if p.strip()]
    if not paragraphs:
        return ""
    return "\n".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs)


def upsert_drafted_letter(
    *,
    recipient_org: str,
    subject: str,
    body: str,
    source_post_url: str = "",
    recipient_email: str = "",
    check_dns: bool = True,
) -> OutreachRecord | None:
    """
    Queue one drafted letter from the news agent in the outreach database.

    This is the bridge: Arshie's agent creates the draft, this function enriches
    the recipient email and stores the draft where Ali/Amine's sender can pick it up.
    """
    init_db()
    email = find_email_for_org(recipient_org, recipient_email, check_dns=check_dns)
    if not email:
        logger.warning("No email found for %s; draft not queued.", recipient_org)
        return None

    db = SessionLocal()
    try:
        record = db.query(OutreachRecord).filter_by(email=email.lower()).first()
        if record is None:
            record = OutreachRecord(
                name=recipient_org,
                email=email.lower(),
                firm=recipient_org,
                focus_area="news-triggered investor/grant outreach",
            )
            db.add(record)

        record.drafted_subject = subject
        record.drafted_body = body
        record.source_post_url = source_post_url
        if not record.sent_at:
            record.pipeline_status = "drafted"
        db.commit()
        db.refresh(record)
        return record
    finally:
        db.close()


def queue_drafted_letters(letters: Iterable[dict], *, check_dns: bool = True) -> BridgeResult:
    result = BridgeResult()
    for letter in letters:
        record = upsert_drafted_letter(
            recipient_org=letter.get("recipient_org", ""),
            recipient_email=letter.get("recipient_email", ""),
            subject=letter.get("subject", ""),
            body=letter.get("body", ""),
            source_post_url=letter.get("source_post_url", ""),
            check_dns=check_dns,
        )
        if record:
            result.queued += 1
        else:
            result.skipped += 1
    return result


def send_queued_drafts(*, limit: int | None = None, dry_run: bool = False) -> BridgeResult:
    """Send drafted-but-not-sent records created by the bridge."""
    init_db()
    result = BridgeResult()
    db = SessionLocal()
    try:
        query = (
            db.query(OutreachRecord)
            .filter(OutreachRecord.sent_at.is_(None))
            .filter(OutreachRecord.drafted_subject.isnot(None))
            .filter(OutreachRecord.drafted_body.isnot(None))
            .order_by(OutreachRecord.created_at.asc())
        )
        records = query.limit(limit).all() if limit else query.all()
    finally:
        db.close()

    for record in records:
        if dry_run:
            logger.info("[DRY RUN] Would send queued draft to %s", record.email)
            result.sent += 1
            continue

        investor = {
            "name": record.name,
            "email": record.email,
            "firm": record.firm or record.name,
            "focus_area": record.focus_area or "",
        }
        message_id = send_and_record(
            investor,
            record.drafted_subject or "CureForge AI outreach",
            text_to_html(record.drafted_body or ""),
        )
        if message_id:
            result.sent += 1
        else:
            result.failed += 1

    return result
