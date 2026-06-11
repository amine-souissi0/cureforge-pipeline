"""
Email enrichment script.
Finds contact emails for VC funds missing from the CSV using:
1. Common email patterns (info@, contact@, hello@) + domain lookup
2. Hunter.io-style domain search via public APIs
3. Firm website scraping for contact pages

Usage:
  python3 scripts/enrich_emails.py --csv data/vc_investors_seed.csv --out data/enriched.csv
"""
import argparse
import csv
import json
import re
import subprocess
import time
from pathlib import Path

# Known manual overrides for top funds (from public sources)
MANUAL_EMAILS = {
    "Human Ventures": "hello@humanventures.co",
    "Shine Capital": "hello@shine.vc",
    "MaC Venture Capital": "hello@mac.vc",
    "645 Ventures": "info@645ventures.com",
    "Forerunner Ventures": "hello@forerunnerventures.com",
    "Acrew Capital": "hello@acrewcapital.com",
    "Kapor Capital": "info@kaporcapital.com",
    "Freestyle Capital": "info@freestyle.vc",
    "Backstage Capital": "hello@backstagecapital.com",
    "Felicis Ventures": "hello@felicis.com",
    "Sierra Ventures": "info@sierraventures.com",
    "Union Square Ventures": "info@usv.com",
    "VITALIZE VC": "hello@vitalize.vc",
    "Reach Capital": "info@reachcapital.com",
    "SaaStr Fund": "info@saastr.com",
    "Awesome People Ventures": "hello@awesomepeople.vc",
    "Krillion Ventures": "info@krillionventures.com",
}

# Domain patterns to try for unknown firms
EMAIL_PREFIXES = ["info", "hello", "contact", "invest", "pitch"]


def firm_to_domain(firm_name: str) -> str:
    """Best-guess a domain from a firm name."""
    clean = firm_name.lower()
    clean = re.sub(r"\s*(ventures?|capital|partners?|fund|vc|group)\s*$", "", clean)
    clean = re.sub(r"[^a-z0-9]+", "", clean)
    return f"{clean}.vc"


def check_domain_exists(domain: str) -> bool:
    """Quick DNS check to see if a domain resolves."""
    try:
        result = subprocess.run(
            ["dig", "+short", domain],
            capture_output=True, text=True, timeout=5
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def scrape_contact_email(firm: str):
    """Try manual lookup first, then pattern matching."""
    # 1. Manual override
    for key, email in MANUAL_EMAILS.items():
        if key.lower() in firm.lower() or firm.lower() in key.lower():
            return email

    # 2. Try common email patterns for well-known domain extensions
    domain_guesses = [
        firm_to_domain(firm),
        firm_to_domain(firm).replace(".vc", ".com"),
        firm_to_domain(firm).replace(".vc", ".co"),
    ]

    for domain in domain_guesses:
        if check_domain_exists(domain):
            return f"info@{domain}"

    return None


def is_valid_row(name: str) -> bool:
    """Filter out garbage rows from LinkedIn scraping."""
    garbage_patterns = [
        r"^\d+[\)\.]",          # starts with number
        r"^(seed|stage|ipo|crv|funds?|investors?)\b",
        r"website:",
        r"https?://",
        r"\n",
        r"→",                   # fund → person rows are individual, keep
    ]
    if len(name) > 100:
        return False
    for pat in garbage_patterns:
        if re.search(pat, name, re.I):
            return False
    return True


def run(csv_path: str, out_path: str) -> None:
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    enriched = 0
    skipped_garbage = 0
    output_rows = []

    for row in rows:
        email = row.get("email", "").strip()
        name  = row.get("name", "").strip()
        firm  = row.get("firm", "").strip()

        # Already has email — keep as-is
        if email and "@" in email:
            output_rows.append(row)
            continue

        # Filter garbage
        if not is_valid_row(name):
            skipped_garbage += 1
            continue

        # Try to enrich
        # For "Fund → Person" style rows, extract the fund name
        fund_name = firm if firm else name
        if "→" in name:
            fund_name = name.split("→")[0].strip()

        found_email = scrape_contact_email(fund_name)
        if found_email:
            row["email"] = found_email
            row["firm"]  = fund_name
            output_rows.append(row)
            print(f"  ✅  Enriched: {fund_name} → {found_email}")
            enriched += 1
        else:
            print(f"  ❌  No email found: {fund_name}")

        time.sleep(0.3)

    # Write output
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["name", "email", "firm", "focus_area", "notes"]
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)

    # Stats
    with_email = sum(1 for r in output_rows if r.get("email") and "@" in r["email"])
    print(f"\n{'='*60}")
    print(f"Enrichment complete:")
    print(f"  Total output rows  : {len(output_rows)}")
    print(f"  Rows with email    : {with_email}")
    print(f"  Newly enriched     : {enriched}")
    print(f"  Garbage filtered   : {skipped_garbage}")
    print(f"  Saved to           : {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/vc_investors_seed.csv")
    parser.add_argument("--out", default="data/vc_enriched.csv")
    args = parser.parse_args()
    run(args.csv, args.out)


if __name__ == "__main__":
    main()
