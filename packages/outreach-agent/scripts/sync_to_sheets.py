"""
Syncs outreach.db status to the 'Agent Pipeline' tab in Google Sheets.

Run manually after each batch:
    python -m scripts.sync_to_sheets

Or schedule it (e.g. every 30 min via cron):
    */30 * * * * cd /path/to/Communication-AI-Agent && python -m scripts.sync_to_sheets
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gspread
from google.oauth2.service_account import Credentials
from models.database import OutreachRecord, SessionLocal, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SHEET_ID = "1yputOAlAet524SxEV9T8pBREmt-Y4yoiYtdwNJg7ZQM"
TAB_NAME = "Agent Pipeline"
CREDS_FILE = str(Path.home() / "Downloads/airy-timing-497013-r3-79e92083bd6e.json")

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


def get_sheet():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    return sh.worksheet(TAB_NAME)


def sync():
    init_db()
    db = SessionLocal()

    try:
        ws = get_sheet()
        all_rows = ws.get_all_values()

        if not all_rows:
            logger.error("Sheet tab is empty — run initial export first")
            return

        headers = all_rows[0]
        email_col = headers.index("Email")
        status_col = headers.index("Agent Status")
        sent_col = headers.index("Sent At")
        reply_status_col = headers.index("Reply Status")
        reply_received_col = headers.index("Reply Received At")
        updated_col = headers.index("Last Updated")

        # Build email -> row index map (1-based, row 1 is header)
        email_to_row = {}
        for i, row in enumerate(all_rows[1:], start=2):
            if len(row) > email_col:
                email_to_row[row[email_col].strip().lower()] = i

        records = db.query(OutreachRecord).all()
        updated = 0
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        for r in records:
            email = (r.email or "").strip().lower()
            row_idx = email_to_row.get(email)

            if not row_idx:
                # New contact not in sheet yet — append it
                ws.append_row([
                    r.name or "",
                    r.email or "",
                    r.firm or "",
                    r.focus_area or "",
                    "",
                    "sent" if r.sent_at else "not_contacted",
                    str(r.sent_at) if r.sent_at else "",
                    r.reply_status.value if r.reply_status else "",
                    str(r.reply_received_at) if r.reply_received_at else "",
                    now,
                ])
                updated += 1
                continue

            # Update existing row
            agent_status = "sent" if r.sent_at else "not_contacted"
            if r.reply_status:
                agent_status = r.reply_status.value

            updates = [
                (row_idx, status_col + 1, agent_status),
                (row_idx, sent_col + 1, str(r.sent_at) if r.sent_at else ""),
                (row_idx, reply_status_col + 1, r.reply_status.value if r.reply_status else ""),
                (row_idx, reply_received_col + 1, str(r.reply_received_at) if r.reply_received_at else ""),
                (row_idx, updated_col + 1, now),
            ]

            for row, col, val in updates:
                ws.update_cell(row, col, val)

            updated += 1

        logger.info(f"Sync complete — {updated} records updated in Google Sheet")

    finally:
        db.close()


if __name__ == "__main__":
    sync()
