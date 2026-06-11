"""
Queue drafted outreach letters into outreach.db.

Input JSON shape:
[
  {
    "recipient_org": "Example Foundation",
    "subject": "Partnership opportunity",
    "body": "Email body",
    "source_post_url": "https://..."
  }
]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.bridge import queue_drafted_letters

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Queue drafted outreach letters.")
    parser.add_argument("--input", required=True, help="Path to JSON array of drafted letters.")
    parser.add_argument(
        "--no-dns-check",
        action="store_true",
        help="Skip DNS validation when guessing org emails.",
    )
    args = parser.parse_args()

    letters = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(letters, list):
        raise SystemExit("Input JSON must be an array of letters.")

    result = queue_drafted_letters(letters, check_dns=not args.no_dns_check)
    print(f"queued={result.queued} skipped={result.skipped}")


if __name__ == "__main__":
    main()
