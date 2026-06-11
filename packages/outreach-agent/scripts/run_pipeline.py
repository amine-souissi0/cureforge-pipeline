"""
Main pipeline runner — runs all automated steps in sequence.

Steps:
  1. Import new contacts from Google Sheet
  2. Send queued outreach emails (new contacts)
  3. Send follow-up emails (no reply after threshold)
  4. Classify and forward new replies to boss (HITL)

Run manually or via cron:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --step import
    python scripts/run_pipeline.py --step outreach
    python scripts/run_pipeline.py --step followup
    python scripts/run_pipeline.py --step hitl
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.email_agent import send_and_record
from agents.personalization import default_subject, personalize
from agents.reply_classifier import classify_reply, forward_to_boss, should_forward
from config.settings import settings
from models.database import OutreachRecord, ReplyStatus, SessionLocal, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
FOLLOWUP_DELAY_DAYS   = 7    # wait 7 days after last send before follow-up
MAX_FOLLOWUPS         = 3    # stop after 3 follow-ups with no reply
OUTREACH_BATCH_LIMIT  = 20   # max new emails per run (rate-limiting)


# ── Step 1: Import from sheet ─────────────────────────────────────────────────
def step_import():
    from scripts.import_from_sheet import sync
    logger.info("=== STEP: Import from Google Sheet ===")
    sync(dry_run=False)


# ── Step 2: Send new outreach emails ─────────────────────────────────────────
def step_outreach():
    logger.info("=== STEP: Send new outreach emails ===")
    db = SessionLocal()
    try:
        pending = (
            db.query(OutreachRecord)
            .filter(
                OutreachRecord.pipeline_status == "queued",
                OutreachRecord.sent_at == None,
            )
            .limit(OUTREACH_BATCH_LIMIT)
            .all()
        )
        logger.info("Found %d queued contacts to email", len(pending))

        for record in pending:
            investor = {
                "name":       record.name,
                "email":      record.email,
                "firm":       record.firm or record.name,
                "focus_area": record.focus_area or "biotech / longevity",
                "notes":      "",
            }
            try:
                html    = personalize(investor)
                subject = default_subject(investor)
                msg_id  = send_and_record(investor, subject, html)
                if msg_id:
                    logger.info("✅ Sent to %s (%s)", record.firm, record.email)
                else:
                    logger.warning("❌ Failed to send to %s", record.email)
            except Exception as e:
                logger.error("Error sending to %s: %s", record.email, e)
    finally:
        db.close()


# ── Step 3: Send follow-up emails ─────────────────────────────────────────────
def _build_followup_html(original_body: str, firm: str, stage: int) -> str:
    """Generate a follow-up via Groq based on the original email."""
    prompt = (
        f"You sent the following outreach email to {firm} (a VC / investor).\n"
        f"They have not replied after {stage * FOLLOWUP_DELAY_DAYS} days.\n"
        f"Write a short, human follow-up (2–3 sentences max). "
        f"Do not repeat the full pitch. Just check in warmly and offer to share more.\n\n"
        f"Original email (text only, ignore HTML):\n{original_body[:1000]}\n\n"
        f"Return ONLY the follow-up body text (no subject, no greeting, no signature)."
    )
    body = json.dumps({
        "model": settings.groq_model or "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system",  "content": "You are a concise startup fundraising assistant."},
            {"role": "user",    "content": prompt},
        ],
        "max_tokens":  150,
        "temperature": 0.7,
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type":  "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        content = json.loads(r.read())["choices"][0]["message"]["content"].strip()

    name_var = firm or "there"
    return f"""<p>Hi {name_var},</p>
<p>{content}</p>
<p>Best,<br/>The LongevityInTime Team</p>"""


def step_followup():
    logger.info("=== STEP: Send follow-up emails ===")
    db = SessionLocal()
    threshold = datetime.utcnow() - timedelta(days=FOLLOWUP_DELAY_DAYS)
    try:
        due = (
            db.query(OutreachRecord)
            .filter(
                OutreachRecord.pipeline_status == "sent",
                OutreachRecord.reply_status == ReplyStatus.PENDING,
                OutreachRecord.sent_at <= threshold,
                OutreachRecord.follow_up_stage < MAX_FOLLOWUPS,
            )
            .all()
        )
        # Also include those whose next_follow_up_at is overdue
        also_due = (
            db.query(OutreachRecord)
            .filter(
                OutreachRecord.pipeline_status == "sent",
                OutreachRecord.reply_status == ReplyStatus.PENDING,
                OutreachRecord.next_follow_up_at != None,
                OutreachRecord.next_follow_up_at <= datetime.utcnow(),
                OutreachRecord.follow_up_stage < MAX_FOLLOWUPS,
            )
            .all()
        )
        records = {r.id: r for r in list(due) + list(also_due)}.values()
        logger.info("Found %d contacts due for follow-up", len(list(records)))

        for record in records:
            stage = (record.follow_up_stage or 0) + 1
            try:
                fu_html = _build_followup_html(
                    record.drafted_body or "", record.firm or record.name, stage
                )
                subject = f"Re: {record.drafted_subject or default_subject({'firm': record.firm})}"
                investor = {"name": record.name, "email": record.email,
                            "firm": record.firm, "focus_area": record.focus_area}
                msg_id = send_and_record(investor, subject, fu_html)
                if msg_id:
                    record.follow_up_stage   = stage
                    record.last_follow_up_at = datetime.utcnow()
                    record.next_follow_up_at = datetime.utcnow() + timedelta(days=FOLLOWUP_DELAY_DAYS)
                    # store follow-up message ids
                    ids = json.loads(record.follow_up_message_ids or "[]")
                    ids.append(msg_id)
                    record.follow_up_message_ids = json.dumps(ids)
                    db.commit()
                    logger.info("✅ Follow-up #%d sent to %s", stage, record.firm)
            except Exception as e:
                logger.error("Follow-up error for %s: %s", record.email, e)
    finally:
        db.close()


# ── Step 4: HITL — classify and forward genuine replies ──────────────────────
def step_hitl():
    """
    Scan for unprocessed replies and:
      - Template/rejection → update status, no forward
      - Interested/needs_info → forward to olegteterinjr@gmail.com
    """
    logger.info("=== STEP: HITL reply classification ===")
    db = SessionLocal()
    try:
        # Find records with raw_reply not yet classified
        unprocessed = (
            db.query(OutreachRecord)
            .filter(
                OutreachRecord.raw_reply != None,
                OutreachRecord.reply_status == ReplyStatus.PENDING,
                OutreachRecord.reply_received_at != None,
            )
            .all()
        )
        logger.info("Found %d unprocessed replies", len(unprocessed))

        for record in unprocessed:
            try:
                result = classify_reply(
                    reply_text = record.raw_reply,
                    sender     = record.email,
                    subject    = record.drafted_subject or "",
                )
                category = result.get("category", "needs_info")
                reason   = result.get("reason",   "")

                # Map category → ReplyStatus
                status_map = {
                    "template":     ReplyStatus.PENDING,   # don't change yet
                    "rejection":    ReplyStatus.NOT_INTERESTED,
                    "interested":   ReplyStatus.INTERESTED,
                    "needs_info":   ReplyStatus.NEEDS_INFO,
                }
                record.reply_status   = status_map.get(category, ReplyStatus.NEEDS_INFO)
                record.pipeline_status = "replied"
                db.commit()

                logger.info(
                    "Classified reply from %s as '%s': %s",
                    record.firm, category, reason
                )

                if should_forward(category):
                    forwarded = forward_to_boss(
                        original_sender  = record.email,
                        original_subject = record.drafted_subject or "",
                        reply_text       = record.raw_reply,
                        firm_name        = record.firm or record.name,
                        category         = category,
                        reason           = reason,
                    )
                    if forwarded:
                        logger.info("→ Forwarded to boss: %s", record.firm)

            except Exception as e:
                logger.error("HITL error for %s: %s", record.email, e)
    finally:
        db.close()


# ── Main ──────────────────────────────────────────────────────────────────────
STEPS = {
    "import":   step_import,
    "outreach": step_outreach,
    "followup": step_followup,
    "hitl":     step_hitl,
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the investor outreach pipeline")
    parser.add_argument(
        "--step",
        choices=list(STEPS.keys()),
        default=None,
        help="Run only a specific step (default: all steps in order)",
    )
    args = parser.parse_args()

    init_db()

    if args.step:
        STEPS[args.step]()
    else:
        for name, fn in STEPS.items():
            try:
                fn()
            except Exception as e:
                logger.error("Step %s failed: %s", name, e)
