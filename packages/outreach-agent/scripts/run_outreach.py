"""
Investor outreach script.

Usage:
    python -m scripts.run_outreach --csv data/investors_sample.csv [--dry-run]

Reads a CSV of investors, skips any already contacted, personalizes an email
with GPT-4, then sends it via Resend and records the result in the database.
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Make sure the project root is on sys.path when run as a module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.email_agent import send_and_record
from agents.personalization import default_subject, personalize
from models.database import OutreachRecord, SessionLocal, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"name", "email", "firm", "focus_area"}


def already_contacted(email: str, db) -> bool:
    record = db.query(OutreachRecord).filter_by(email=email).first()
    return record is not None and record.sent_at is not None


def run(csv_path: str, dry_run: bool = False) -> None:
    init_db()
    db = SessionLocal()

    try:
        df = pd.read_csv(csv_path)
        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            logger.error("CSV is missing required columns: %s", missing)
            sys.exit(1)

        # Fill optional 'notes' column if absent
        if "notes" not in df.columns:
            df["notes"] = ""

        total = len(df)
        sent = skipped = failed = 0

        for _, row in df.iterrows():
            investor = row.to_dict()
            email = str(investor.get("email", "")).strip()

            if not email:
                logger.warning("Row has no email, skipping: %s", investor)
                skipped += 1
                continue

            if already_contacted(email, db):
                logger.info("Already contacted %s — skipping.", email)
                skipped += 1
                continue

            subject = default_subject(investor)

            if dry_run:
                logger.info("[DRY RUN] Would send to %s | Subject: %s", email, subject)
                sent += 1
                continue

            try:
                html_body = personalize(investor)
            except Exception as exc:
                logger.error("Personalization failed for %s: %s", email, exc)
                failed += 1
                continue

            message_id = send_and_record(investor, subject, html_body)
            if message_id:
                logger.info("Sent to %s (message_id=%s)", email, message_id)
                sent += 1
            else:
                logger.error("Sending failed for %s", email)
                failed += 1

        logger.info(
            "Outreach complete. Total=%d | Sent=%d | Skipped=%d | Failed=%d",
            total,
            sent,
            skipped,
            failed,
        )

    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Investor outreach sender")
    parser.add_argument(
        "--csv",
        default="data/investors_sample.csv",
        help="Path to the investor CSV file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be sent without actually sending",
    )
    args = parser.parse_args()
    run(args.csv, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
