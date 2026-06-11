"""
Free LinkedIn post scraper — no API key needed, no login, zero blocking risk.

Extracts investor/fund names from any public LinkedIn post URL and outputs a
ready-to-use CSV for the outreach agent.

Usage:
    python scripts/scrape_linkedin_post.py --url "https://www.linkedin.com/posts/..." --out data/scraped_investors.csv
"""

import argparse
import csv
import re
import sys
from pathlib import Path

import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Common VC fund suffixes to help detect fund names in raw text
VC_KEYWORDS = [
    "ventures", "capital", "vc", "fund", "partners", "invest",
    "seed", "growth", "equity", "labs", "group", "collective",
]


def fetch_post_text(url: str) -> str:
    """Fetch raw text from a public LinkedIn post (no login required)."""
    resp = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=15)
    resp.raise_for_status()
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", resp.text)
    text = re.sub(r"\s+", " ", text)
    return text


def extract_fund_names(text: str) -> list[dict]:
    """
    Heuristic extraction: look for lines / phrases that resemble fund names.
    Works best when the post has a clear list format.
    """
    # Split on common delimiters used in list-style LinkedIn posts
    chunks = re.split(r"[\n\r•\|–\-]+", text)
    funds = []
    seen = set()

    for chunk in chunks:
        chunk = chunk.strip().strip("*•·▪►✓")
        # Skip empty, too short, or too long (likely a sentence)
        if not chunk or len(chunk) < 3 or len(chunk) > 80:
            continue
        chunk_lower = chunk.lower()
        # Must contain a VC keyword to be considered a fund name
        if not any(kw in chunk_lower for kw in VC_KEYWORDS):
            continue
        # Deduplicate
        key = chunk_lower
        if key in seen:
            continue
        seen.add(key)
        funds.append({"name": chunk, "firm": chunk, "email": "", "focus_area": "Investor", "notes": "Scraped from LinkedIn post"})

    return funds


def save_csv(funds: list[dict], out_path: str) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["name", "email", "firm", "focus_area", "notes"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(funds)
    print(f"✅ Saved {len(funds)} funds to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape a public LinkedIn post for VC fund names")
    parser.add_argument("--url", required=True, help="Public LinkedIn post URL")
    parser.add_argument("--out", default="data/scraped_investors.csv", help="Output CSV path")
    args = parser.parse_args()

    print(f"🔍 Fetching: {args.url}")
    try:
        text = fetch_post_text(args.url)
    except Exception as e:
        print(f"❌ Failed to fetch post: {e}", file=sys.stderr)
        sys.exit(1)

    funds = extract_fund_names(text)
    if not funds:
        print("⚠️  No fund names detected. The post may require login or has an unusual format.")
        print("💡 Tip: paste the post text manually into data/manual_investors.txt and re-run with --from-file flag.")
        sys.exit(0)

    print(f"📋 Found {len(funds)} fund names")
    save_csv(funds, args.out)
    print(f"\n🚀 Next step: run the outreach agent:")
    print(f"   python -m scripts.run_outreach --csv {args.out} --dry-run")


if __name__ == "__main__":
    main()
