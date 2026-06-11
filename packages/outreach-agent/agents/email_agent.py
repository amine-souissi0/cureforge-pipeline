import logging
import time
from datetime import datetime
from typing import Optional

import resend

from config.settings import settings
from models.database import OutreachRecord, SessionLocal

logger = logging.getLogger(__name__)

resend.api_key = settings.resend_api_key

# Resend free tier: 3,000 emails/month; keep a small delay to avoid bursting
_SEND_DELAY_SECONDS = 0.5


def send_email(
    to: str,
    subject: str,
    html_body: str,
    from_email: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> str:
    """
    Send a single email via Resend and return the message ID.

    Raises:
        Exception: propagated from Resend SDK on failure.
    """
    sender = from_email or settings.from_email
    params: resend.Emails.SendParams = {
        "from": sender,
        "to": [to],
        "subject": subject,
        "html": html_body,
    }
    response_address = reply_to or settings.reply_to_email
    if response_address:
        params["reply_to"] = response_address
    response = resend.Emails.send(params)
    message_id: str = response["id"]
    logger.info("Email sent to %s — message_id=%s", to, message_id)
    time.sleep(_SEND_DELAY_SECONDS)
    return message_id


def send_and_record(
    investor: dict,
    subject: str,
    html_body: str,
) -> Optional[str]:
    """
    Send an email and persist (or update) the OutreachRecord in the database.

    Returns the Resend message ID on success, or None if sending fails.
    """
    db = SessionLocal()
    try:
        message_id = send_email(
            to=investor["email"],
            subject=subject,
            html_body=html_body,
        )

        record = db.query(OutreachRecord).filter_by(email=investor["email"]).first()
        if record is None:
            record = OutreachRecord(
                name=investor.get("name", ""),
                email=investor["email"],
                firm=investor.get("firm", ""),
                focus_area=investor.get("focus_area", ""),
            )
            db.add(record)

        record.sent_at = datetime.utcnow()
        record.message_id = message_id
        record.drafted_subject = subject
        record.drafted_body = html_body
        record.pipeline_status = "sent"
        db.commit()
        return message_id

    except Exception as exc:
        db.rollback()
        logger.error("Failed to send email to %s: %s", investor.get("email"), exc)
        return None

    finally:
        db.close()
