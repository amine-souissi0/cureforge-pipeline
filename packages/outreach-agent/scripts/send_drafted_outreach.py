"""
Send outreach drafts queued by the longevity news bridge.

Preview first:
    python -m scripts.send_drafted_outreach --dry-run

Send live:
    python -m scripts.send_drafted_outreach --limit 25
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.bridge import send_queued_drafts

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send queued outreach drafts.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum drafts to send.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending.")
    args = parser.parse_args()

    result = send_queued_drafts(limit=args.limit, dry_run=args.dry_run)
    print(
        "Draft outreach complete: "
        f"sent={result.sent} failed={result.failed} skipped={result.skipped}"
    )


if __name__ == "__main__":
    main()
