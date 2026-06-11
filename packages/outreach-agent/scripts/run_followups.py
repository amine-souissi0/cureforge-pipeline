"""
Send Day 3 and Day 7 follow-ups for non-responders.

Preview first:
    python -m scripts.run_followups --dry-run

Send live:
    python -m scripts.run_followups --limit 50
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.followup_agent import run_due_follow_ups

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run due outreach follow-ups.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum records to scan.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending.")
    args = parser.parse_args()

    result = run_due_follow_ups(limit=args.limit, dry_run=args.dry_run)
    print(
        "Follow-ups complete: "
        f"due={result.due} sent={result.sent} failed={result.failed} skipped={result.skipped}"
    )


if __name__ == "__main__":
    main()
