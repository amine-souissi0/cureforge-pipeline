"""
Two-way sync between Google Sheet and outreach.db.

READ  (always works):  downloads xlsx via public link, parses email contacts
WRITE (requires key):  writes pipeline_status back to the sheet using gspread

Service account key path: secrets/gcp_service_account.json
Sheet email must be shared with: aminisouissi@airy-timing-497013-r3.iam.gserviceaccount.com

Run:
    python scripts/sync_sheet.py              # full two-way sync
    python scripts/sync_sheet.py --read-only  # import only, no write-back
    python scripts/sync_sheet.py --dry-run    # print what would change
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CREDS_PATH = ROOT / "secrets" / "gcp_service_account.json"
SHEET_ID = "1k0d48m9Nf1MTUAGptIurRpSg030Wp88m"
SHEET_EXPORT_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"
TARGET_TAB = "Лагун Е.С."

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Russian → our pipeline status
RU_TO_STATUS = {
    "Готово":        "sent",
    "Не начато":     "queued",
    "-":             "queued",
    "Стоп":          "closed",
    "Мало дают":     "closed",
    "Мало данных":   "closed",
    "Не актуально":  "closed",
}

# Our pipeline status → Russian (for write-back)
STATUS_TO_RU = {
    "queued":   "Не начато",
    "sent":     "Готово",
    "replied":  "Готово",     # show as done in sheet
    "closed":   "Стоп",
}


def _download_xlsx() -> bytes:
    """Download sheet as xlsx — tries Drive API first (needs service account), falls back to public URL."""
    if CREDS_PATH.exists():
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaIoBaseDownload
            import warnings; warnings.filterwarnings("ignore")
            creds = Credentials.from_service_account_file(
                str(CREDS_PATH),
                scopes=["https://www.googleapis.com/auth/drive.readonly"],
            )
            drive = build("drive", "v3", credentials=creds)
            request = drive.files().get_media(fileId=SHEET_ID)
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buf.getvalue()
        except Exception as e:
            print(f"   Drive API failed ({e}), falling back to public URL")

    req = urllib.request.Request(SHEET_EXPORT_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _parse_xlsx(xlsx_bytes: bytes) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb[TARGET_TAB]
    rows = []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        company    = str(row[0] or "").strip()
        col2       = str(row[1] or "").strip()
        status_raw = str(row[2] or "").strip()
        comment    = str(row[3] or "").strip() or None
        row_id     = str(row[4] or "").strip() if len(row) > 4 else None
        m = EMAIL_RE.search(col2)
        if not m:
            continue
        rows.append({
            "row_num":   i,
            "name":      company,
            "email":     m.group(0).lower(),
            "firm":      company,
            "focus_area": "longevity / biotech VC",
            "pipeline_status": RU_TO_STATUS.get(status_raw, "queued"),
            "sheet_status":    status_raw,
            "sheet_id":  row_id,
            "comment":   comment,
        })
    return rows


def _gspread_client():
    """Return authenticated gspread client using service account key."""
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(str(CREDS_PATH), scopes=scopes)
    return gspread.authorize(creds)


def sync(read_only: bool = False, dry_run: bool = False) -> None:
    import sys
    sys.path.insert(0, str(ROOT))
    from models.database import OutreachRecord, SessionLocal, init_db
    init_db()

    print("📥 Downloading Google Sheet…")
    xlsx = _download_xlsx()
    contacts = _parse_xlsx(xlsx)
    print(f"   Parsed {len(contacts)} contacts with email")

    db = SessionLocal()
    added = updated_db = skipped = 0
    rows_to_writeback: list[tuple[int, str]] = []  # (row_num, new_ru_status)

    try:
        for c in contacts:
            existing = db.query(OutreachRecord).filter_by(email=c["email"]).first()
            order = ["queued", "sent", "replied", "closed"]

            if existing:
                cur_idx = order.index(existing.pipeline_status) if existing.pipeline_status in order else 0
                new_idx = order.index(c["pipeline_status"]) if c["pipeline_status"] in order else 0

                if new_idx > cur_idx:
                    if not dry_run:
                        existing.pipeline_status = c["pipeline_status"]
                        if c["pipeline_status"] == "sent" and not existing.sent_at:
                            existing.sent_at = datetime.utcnow()
                    updated_db += 1
                    print(f"   ↑ Updated DB: {c['firm']} → {c['pipeline_status']}")
                else:
                    skipped += 1
                    # Check if our DB is further ahead — write back to sheet
                    if cur_idx > new_idx and not read_only:
                        rows_to_writeback.append((c["row_num"], STATUS_TO_RU.get(existing.pipeline_status, "Готово")))
            else:
                if not dry_run:
                    record = OutreachRecord(
                        name=c["name"], email=c["email"], firm=c["firm"],
                        focus_area=c["focus_area"],
                        pipeline_status=c["pipeline_status"],
                        sent_at=datetime.utcnow() if c["pipeline_status"] == "sent" else None,
                    )
                    db.add(record)
                added += 1
                print(f"   + Added: {c['firm']} ({c['pipeline_status']})")

        if not dry_run:
            db.commit()
    finally:
        db.close()

    marker = "[DRY RUN] " if dry_run else ""
    print(f"\n{marker}DB: +{added} added, ~{updated_db} updated, {skipped} unchanged")

    # ── Write-back to sheet ───────────────────────────────────────────────────
    if read_only or dry_run or not rows_to_writeback:
        if rows_to_writeback:
            print(f"   (skipping write-back of {len(rows_to_writeback)} rows — read_only={read_only})")
        return

    if not CREDS_PATH.exists():
        print(f"⚠  No service account key at {CREDS_PATH} — skipping write-back")
        return

    try:
        print(f"\n📤 Writing {len(rows_to_writeback)} status updates back to sheet…")
        gc = _gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(TARGET_TAB)
        for row_num, ru_status in rows_to_writeback:
            if not dry_run:
                ws.update_cell(row_num, 3, ru_status)  # col C = status
            print(f"   ✓ Row {row_num} → {ru_status}")
        print("   Write-back done.")
    except Exception as e:
        print(f"⚠  Write-back failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--dry-run",   action="store_true")
    args = parser.parse_args()
    sync(read_only=args.read_only, dry_run=args.dry_run)
