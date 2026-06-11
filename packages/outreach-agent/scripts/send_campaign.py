"""
Campaign sender — uses exact email text from boss.
Usage:
  python3 scripts/send_campaign.py --csv data/vc_investors_seed.csv [--dry-run] [--press-release path/to/pr.txt]
"""
import argparse
import csv
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ── config ────────────────────────────────────────────────────────────────────
API_KEY   = "re_CYLGLjBT_9sy6mvLoENMLgAP3MmV9bXSX"
FROM_EMAIL = "outreach@contact.longevityintime.org"
RATE_LIMIT_DELAY = 1.5   # seconds between sends (stay inside free tier)

SUBJECT = "CureForge AI – The Autonomous Research Federation for Longevity (NVIDIA Inception Member)"

BODY_TEMPLATE = """\
<p>Hi {name},</p>

<p>We are building <strong>CureForge AI</strong>: the world's first autonomous research federation for longevity.</p>

<p>Not a tool. Not a CRO. A <strong>self‑operating system of specialized AI institutes</strong> – coordinated through a single knowledge graph, a cross‑institute routing layer, and a unified autonomous orchestrator. It runs 24/7, from raw data to blinded and prospective simulations, all the way to scientific articles, intellectual property, investor materials, and FDA‑ready submission packages.</p>

<p>We are an active member of the <strong>NVIDIA Inception Program</strong>.</p>

<p><strong>Why we are different – the federation is the differentiator.</strong><br>
Individual labs do in‑silico work. We run a federation. Every institute has its own agent stack, knowledge graph, and NVIDIA‑accelerated infrastructure, all coordinated centrally. The unit of competition is the federation, not any single pipeline.</p>

<p><strong>Scale is the sales pitch.</strong><br>
Operational today – ahead of OpenAI's 2028 target.<br>
Our autonomous orchestrator is live in code, already seeded with Alzheimer's, Diabetes, and Cancer pilots.</p>

{press_release_section}

<p>If our vision of how aging can be defeated aligns with yours, I would welcome the opportunity to show you a demo.</p>

<p>Thank you for your consideration.</p>

<p>Best regards,<br>
<strong>Oleg Teterin</strong><br>
Founder &amp; CEO, CureForge AI<br>
<a href="mailto:teterin@intime.digital">teterin@intime.digital</a></p>
"""

PR_SECTION_TEMPLATE = """\
<hr>
<p><strong>📰 Press Release</strong></p>
<blockquote style="border-left:3px solid #ccc;padding-left:1em;color:#444;">
{pr_html}
</blockquote>
"""


def load_press_release(path: str) -> str:
    if not path:
        return ""
    text = Path(path).read_text(encoding="utf-8")
    # Convert plain text to simple HTML paragraphs
    paragraphs = [f"<p>{p.strip()}</p>" for p in text.split("\n\n") if p.strip()]
    return PR_SECTION_TEMPLATE.format(pr_html="\n".join(paragraphs))


def send_email(to_email: str, to_name: str, subject: str, html_body: str) -> dict:
    """Send via subprocess curl to avoid Cloudflare 1010 blocks on Python urllib."""
    payload = json.dumps({
        "from": FROM_EMAIL,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "reply_to": "teterin@intime.digital"
    })

    # Write payload to temp file to avoid shell escaping issues
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write(payload)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [
                "curl", "-s",
                "-X", "POST", "https://api.resend.com/emails",
                "-H", f"Authorization: Bearer {API_KEY}",
                "-H", "Content-Type: application/json",
                "-d", f"@{tmp_path}"
            ],
            capture_output=True, text=True, timeout=30
        )
        return json.loads(result.stdout)
    except Exception as e:
        return {"error": str(e)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def run(csv_path: str, dry_run: bool, press_release_path: str) -> None:
    pr_section = load_press_release(press_release_path)

    sent = skipped = failed = 0
    rows = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Loaded {len(rows)} investors from {csv_path}")
    print(f"Sender: {FROM_EMAIL}\n{'-'*60}")

    for row in rows:
        name  = row.get("name", "").strip()
        email = row.get("email", "").strip()
        firm  = row.get("firm", "").strip()

        if not email or "@" not in email:
            print(f"  ⏭  Skipping '{name}' — no valid email")
            skipped += 1
            continue

        # personalise greeting
        display_name = name if name else (firm if firm else "Investor")
        html_body = BODY_TEMPLATE.format(
            name=display_name,
            press_release_section=pr_section
        )

        if dry_run:
            print(f"  📧  [DRY RUN] Would send to {email} ({display_name})")
            sent += 1
            continue

        result = send_email(email, display_name, SUBJECT, html_body)
        if "id" in result:
            print(f"  ✅  Sent to {email} ({display_name}) → id={result['id']}")
            sent += 1
        else:
            print(f"  ❌  Failed for {email}: {result.get('error', result)}")
            failed += 1

        time.sleep(RATE_LIMIT_DELAY)

    print(f"\n{'='*60}")
    print(f"Campaign complete: Total={len(rows)} | Sent={sent} | Skipped={skipped} | Failed={failed}")


def main():
    parser = argparse.ArgumentParser(description="CureForge investor campaign sender")
    parser.add_argument("--csv", default="data/vc_investors_seed.csv")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--press-release", default="", help="Optional path to press release .txt file")
    args = parser.parse_args()
    run(args.csv, args.dry_run, args.press_release)


if __name__ == "__main__":
    main()
