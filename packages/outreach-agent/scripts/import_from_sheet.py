"""
Import contacts from the boss's Google Sheet into outreach.db.

The sheet has 3 tabs:
  - Лагун Е.С.  : 1000-row master list — email contacts are here
  - Лист1        : accelerator applications (form-only, no emails)
  - Фонд         : VC funds (form-only, no emails)

Only rows with a real email address in column 2 are imported.
Status mapping (Russian → pipeline_status):
  Готово        → sent
  Не начато     → queued
  -             → queued
  Стоп          → closed
  Мало дают     → closed
  Не актуально  → closed

Run:
    python scripts/import_from_sheet.py
    python scripts/import_from_sheet.py --dry-run
"""

from __future__ import annotations

import argparse
import io
import re
import urllib.request
from datetime import datetime

SHEET_EXPORT_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1k0d48m9Nf1MTUAGptIurRpSg030Wp88m"
    "/export?format=xlsx"
)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

STATUS_MAP = {
    "Готово":        "sent",
    "Не начато":     "queued",
    "-":             "queued",
    "Стоп":          "closed",
    "Мало дают":     "closed",
    "Мало данных":   "closed",
    "Не актуально":  "closed",
}


def _download_sheet() -> bytes:
    req = urllib.request.Request(SHEET_EXPORT_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _parse_contacts(xlsx_bytes: bytes) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb["Лагун Е.С."]
    contacts = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        company = str(row[0] or "").strip()
        col2    = str(row[1] or "").strip()
        status_raw = str(row[2] or "").strip()
        comment    = str(row[3] or "").strip() or None

        m = EMAIL_RE.search(col2)
        if not m:
            continue

        email          = m.group(0).lower()
        pipeline_status = STATUS_MAP.get(status_raw, "queued")

        contacts.append(
            {
                "name":            company,
                "email":           email,
                "firm":            company,
                "focus_area":      "longevity / biotech VC",
                "pipeline_status": pipeline_status,
                "source_note":     comment,
            }
        )
    return contacts


def sync(dry_run: bool = False) -> None:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from models.database import OutreachRecord, SessionLocal, init_db

    init_db()
    print("Downloading sheet…")
    xlsx = _download_sheet()
    contacts = _parse_contacts(xlsx)
    print(f"Parsed {len(contacts)} contacts with email from sheet.")

    db = SessionLocal()
    added = updated = skipped = 0
    try:
        for c in contacts:
            existing = db.query(OutreachRecord).filter_by(email=c["email"]).first()
            if existing:
                # Update pipeline status only if not already further along
                order = ["queued", "sent", "replied", "closed"]
                cur_idx  = order.index(existing.pipeline_status or "queued") if (existing.pipeline_status or "queued") in order else 0
                new_idx  = order.index(c["pipeline_status"])  if c["pipeline_status"] in order else 0
                if new_idx > cur_idx:
                    if not dry_run:
                        existing.pipeline_status = c["pipeline_status"]
                        if c["pipeline_status"] == "sent" and not existing.sent_at:
                            existing.sent_at = datetime.utcnow()
                    updated += 1
                else:
                    skipped += 1
            else:
                if not dry_run:
                    record = OutreachRecord(
                        name            = c["name"],
                        email           = c["email"],
                        firm            = c["firm"],
                        focus_area      = c["focus_area"],
                        pipeline_status = c["pipeline_status"],
                        # mark as sent if sheet says so
                        sent_at         = datetime.utcnow() if c["pipeline_status"] == "sent" else None,
                    )
                    db.add(record)
                added += 1

        if not dry_run:
            db.commit()
    finally:
        db.close()

    marker = "[DRY RUN] " if dry_run else ""
    print(f"{marker}Added: {added}  Updated: {updated}  Skipped (already up-to-date): {skipped}")
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Parse and count without writing to DB")
    args = parser.parse_args()
    sync(dry_run=args.dry_run)
