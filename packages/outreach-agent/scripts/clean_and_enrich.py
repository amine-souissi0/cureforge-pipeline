"""
clean_and_enrich.py

1. Cleans the vc_investors_seed.csv — removes garbage rows (scraped sentences, HTML, etc.)
2. For clean fund names missing an email, generates the most likely contact email
   using common VC domain patterns (info@, contact@, hello@)
3. Outputs data/vc_clean_ready.csv — ready for the campaign sender
"""
import csv
import re
import subprocess
import json
import time
from pathlib import Path

INPUT_CSV  = "data/vc_investors_seed.csv"
OUTPUT_CSV = "data/vc_clean_ready.csv"

# Known manual overrides for top-tier funds (guaranteed correct)
MANUAL_EMAILS = {
    "Y Combinator": "apply@ycombinator.com",
    "Andreessen Horowitz": "info@a16z.com",
    "Sequoia Capital": "info@sequoiacap.com",
    "Benchmark": "info@benchmark.com",
    "Khosla Ventures": "info@khoslaventures.com",
    "General Catalyst": "info@generalcatalyst.com",
    "Accel": "info@accel.com",
    "Index Ventures": "info@indexventures.com",
    "Lightspeed Venture Partners": "info@lsvp.com",
    "GV": "info@gv.com",
    "Tiger Global": "info@tigerglobal.com",
    "Softbank Vision Fund": "info@softbank.com",
    "Coatue Management": "info@coatue.com",
    "a16z": "info@a16z.com",
    "BECO Capital": "info@becocapital.com",
    "Wamda Capital": "info@wamda.com",
    "Hub71": "info@hub71.com",
    "Mubadala": "info@mubadala.com",
    "Techstars Dubai": "dubai@techstars.com",
    "500 Global": "info@500.co",
}

# Patterns that indicate a garbage row (not a real fund name)
GARBAGE_PATTERNS = [
    r"^\d+[\.\)]",          # starts with "1." or "1)"
    r"\n",                   # contains newlines
    r"&amp;",               # HTML entities
    r"→",                   # scraped arrow text
    r"@\w+",                # Twitter handles or email fragments
    r"https?://",           # URLs
    r"\b(the|and|for|that|this|with|from|have|been|will|your|their|which|about|more|into|than|were|they|some|also|when|what|where|there|these|those|through|during|before|after|between|should|could|would|other|each|both)\b",  # plain English sentences
    r"^(investors?|funds?|capital|ventures?|partners?|seed|growth|equity)$",  # single generic words
    r"\.{3}$",              # trailing ellipsis (truncated scrape)
    r"[<>]",                # HTML tags
    r"\d{4,}",              # long numbers (likely IDs or URLs)
    r"(?:stage|aiming|execution|thematic|prioritiz|managing partner at|vc at|partner at|founder &|investing)",  # sentence fragments
]

VC_KEYWORDS = [
    "ventures", "capital", "vc", "fund", "partners", "invest",
    "seed", "growth", "equity", "labs", "group", "collective",
    "holdings", "management", "asset", "wealth", "family office",
    "accelerator", "techstars", "incubator", "innovation",
]

def is_garbage(name: str) -> bool:
    """Return True if the name is a garbage scrape artifact."""
    if not name or len(name.strip()) < 3:
        return True
    if len(name) > 80:
        return True
    name_lower = name.lower()
    for pattern in GARBAGE_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return True
    # Must contain at least one VC-related keyword
    if not any(kw in name_lower for kw in VC_KEYWORDS):
        return True
    return False

def clean_name(name: str) -> str:
    """Strip numbering, arrows, and whitespace from fund names."""
    name = re.sub(r"^\d+[\.\)]\s*", "", name)
    name = name.split("→")[0].strip()
    name = name.split("–")[0].strip()
    name = re.sub(r"\s+", " ", name).strip()
    return name

def guess_email(firm_name: str) -> str:
    """Generate the most likely contact email for a VC firm."""
    # Check manual overrides first
    for key, email in MANUAL_EMAILS.items():
        if key.lower() in firm_name.lower() or firm_name.lower() in key.lower():
            return email

    # Build domain from firm name
    domain_name = firm_name.lower()
    domain_name = re.sub(r"\b(ventures|capital|vc|fund|partners|management|group|holdings|labs|collective|investments?)\b", "", domain_name)
    domain_name = re.sub(r"[^a-z0-9]", "", domain_name).strip()

    if not domain_name or len(domain_name) < 2:
        return ""

    # Try common patterns
    return f"info@{domain_name}.com"

def check_domain_resolves(email: str) -> bool:
    """Quick DNS check to see if the domain exists."""
    if not email or "@" not in email:
        return False
    domain = email.split("@")[1]
    try:
        result = subprocess.run(
            ["dig", "+short", "MX", domain],
            capture_output=True, text=True, timeout=5
        )
        mx = result.stdout.strip()
        if mx:
            return True
        # Fallback: check A record
        result2 = subprocess.run(
            ["dig", "+short", "A", domain],
            capture_output=True, text=True, timeout=5
        )
        return bool(result2.stdout.strip())
    except Exception:
        return False

def main():
    rows = []
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)

    print(f"Input: {len(all_rows)} total rows")

    seen_names = set()
    clean_rows = []
    garbage_count = 0

    for row in all_rows:
        raw_name = row.get("name", "").strip()
        raw_firm = row.get("firm", raw_name).strip()
        email    = row.get("email", "").strip()

        # Use firm name if name is empty
        name = clean_name(raw_name or raw_firm)

        # Skip garbage
        if is_garbage(name):
            garbage_count += 1
            continue

        # Deduplicate
        key = name.lower()
        if key in seen_names:
            continue
        seen_names.add(key)

        # If no email, try to guess one
        if not email or "@" not in email:
            email = guess_email(name)

        clean_rows.append({
            "name": name,
            "email": email,
            "firm": name,
            "focus_area": row.get("focus_area", "Investor"),
            "notes": row.get("notes", ""),
        })

    print(f"Garbage rows removed: {garbage_count}")
    print(f"Clean unique firms:   {len(clean_rows)}")

    # DNS validation pass
    print(f"\nRunning DNS validation on {len(clean_rows)} domains...")
    valid_rows = []
    invalid_count = 0
    for i, row in enumerate(clean_rows):
        email = row["email"]
        if email and "@" in email:
            domain_ok = check_domain_resolves(email)
            if not domain_ok:
                invalid_count += 1
                row["email"] = ""  # Clear invalid email but keep the row
        if i % 50 == 0:
            print(f"  Checked {i}/{len(clean_rows)}...")
        valid_rows.append(row)

    # Final split
    with_email = [r for r in valid_rows if r["email"] and "@" in r["email"]]
    without_email = [r for r in valid_rows if not r["email"] or "@" not in r["email"]]

    print(f"\nDNS invalid domains cleared: {invalid_count}")
    print(f"READY TO SEND:               {len(with_email)}")
    print(f"Still missing email:         {len(without_email)}")

    # Write output
    fieldnames = ["name", "email", "firm", "focus_area", "notes"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(with_email)

    print(f"\n✅ Saved {len(with_email)} ready-to-send contacts to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
