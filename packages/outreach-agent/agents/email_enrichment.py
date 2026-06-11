import re
import subprocess


KNOWN_EMAILS = {
    "Y Combinator": "apply@ycombinator.com",
    "Andreessen Horowitz": "info@a16z.com",
    "a16z": "info@a16z.com",
    "Sequoia Capital": "info@sequoiacap.com",
    "Khosla Ventures": "info@khoslaventures.com",
    "General Catalyst": "info@generalcatalyst.com",
    "Accel": "info@accel.com",
    "Index Ventures": "info@indexventures.com",
    "Lightspeed Venture Partners": "info@lsvp.com",
    "First Round Capital": "pitch@firstround.com",
    "Bessemer Venture Partners": "info@bvp.com",
    "Founders Fund": "info@foundersfund.com",
    "500 Global": "info@500.co",
    "Techstars": "info@techstars.com",
    "Felicis Ventures": "hello@felicis.com",
}


def normalize_org_name(org_name: str) -> str:
    clean = (org_name or "").lower()
    clean = re.sub(
        r"\b(ventures|capital|partners|fund|vc|group|management|holdings|labs|collective|investments?)\b",
        "",
        clean,
    )
    return re.sub(r"[^a-z0-9]", "", clean).strip()


def domain_has_dns(domain: str) -> bool:
    try:
        result = subprocess.run(
            ["dig", "+short", "MX", domain],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.stdout.strip():
            return True
        result = subprocess.run(
            ["dig", "+short", "A", domain],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def find_email_for_org(org_name: str, existing_email: str = "", check_dns: bool = True) -> str:
    """Find a usable outreach email from a known list or conservative domain guess."""
    if existing_email and "@" in existing_email:
        return existing_email.strip()

    for key, email in KNOWN_EMAILS.items():
        if key.lower() in org_name.lower() or org_name.lower() in key.lower():
            return email

    clean = normalize_org_name(org_name)
    if len(clean) < 2:
        return ""

    for tld in [".com", ".vc", ".co", ".org", ".io"]:
        domain = f"{clean}{tld}"
        if not check_dns or domain_has_dns(domain):
            return f"info@{domain}"

    return ""
