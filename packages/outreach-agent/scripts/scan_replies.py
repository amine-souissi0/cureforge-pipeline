"""
Scan an IMAP inbox for investor replies and classify them.

The Resend webhook remains the preferred live path. This script is useful when
replies land in a regular mailbox.

Run:
    python -m scripts.scan_replies --limit 50
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.reply_scanner import scan_imap_replies

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan IMAP replies.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum unread messages to scan.")
    parser.add_argument("--mark-seen", action="store_true", help="Mark matched replies as seen.")
    args = parser.parse_args()

    result = scan_imap_replies(limit=args.limit, mark_seen=args.mark_seen)
    print(
        "Reply scan complete: "
        f"scanned={result.scanned} matched={result.matched} "
        f"ignored={result.ignored} failed={result.failed}"
    )


if __name__ == "__main__":
    main()
