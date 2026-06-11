import imaplib
import logging
from dataclasses import dataclass
from datetime import datetime
from email import message_from_bytes
from email.message import Message
from email.utils import parseaddr

from agents.intent_parser import parse_intent
from config.settings import settings
from models.database import OutreachRecord, SessionLocal, init_db

logger = logging.getLogger(__name__)


@dataclass
class ReplyScanResult:
    scanned: int = 0
    matched: int = 0
    ignored: int = 0
    failed: int = 0


def extract_text(message: Message) -> str:
    if message.is_multipart():
        html_fallback = ""
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition:
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if content_type == "text/plain":
                return text
            if content_type == "text/html" and not html_fallback:
                html_fallback = text
        return html_fallback

    payload = message.get_payload(decode=True)
    if payload:
        charset = message.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    return str(message.get_payload() or "")


def record_reply(sender_email: str, body_text: str) -> bool:
    intent = parse_intent(body_text)
    db = SessionLocal()
    try:
        record = db.query(OutreachRecord).filter_by(email=sender_email.lower()).first()
        if record is None:
            return False
        record.reply_status = intent
        record.reply_received_at = datetime.utcnow()
        record.raw_reply = body_text[:4000]
        record.pipeline_status = intent.value
        db.commit()
        return True
    finally:
        db.close()


def scan_imap_replies(*, limit: int = 50, mark_seen: bool = False) -> ReplyScanResult:
    if not settings.imap_host or not settings.imap_user or not settings.imap_password:
        raise ValueError("IMAP_HOST, IMAP_USER, and IMAP_PASSWORD must be configured.")

    init_db()
    result = ReplyScanResult()
    mailbox = imaplib.IMAP4_SSL(settings.imap_host)
    try:
        mailbox.login(settings.imap_user, settings.imap_password)
        mailbox.select(settings.imap_folder)
        status, data = mailbox.search(None, "UNSEEN")
        if status != "OK":
            raise RuntimeError(f"IMAP search failed: {status}")

        ids = data[0].split()[:limit]
        for msg_id in ids:
            result.scanned += 1
            try:
                status, fetched = mailbox.fetch(msg_id, "(BODY.PEEK[])")
                if status != "OK" or not fetched or not fetched[0]:
                    result.failed += 1
                    continue

                raw_message = fetched[0][1]
                message = message_from_bytes(raw_message)
                sender_email = parseaddr(message.get("From", ""))[1].lower().strip()
                body_text = extract_text(message)
                if not sender_email or not body_text:
                    result.ignored += 1
                    continue

                if record_reply(sender_email, body_text):
                    result.matched += 1
                    if mark_seen:
                        mailbox.store(msg_id, "+FLAGS", "\\Seen")
                else:
                    result.ignored += 1
            except Exception as exc:
                logger.error("Failed processing IMAP message %s: %s", msg_id, exc)
                result.failed += 1

        return result
    finally:
        try:
            mailbox.logout()
        except Exception:
            pass
