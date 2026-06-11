"""
Quick test email sender — uses the configured RESEND_API_KEY and FROM_EMAIL
to send a test message to outreach@longevityintime.org
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import resend
from config.settings import settings

resend.api_key = settings.resend_api_key

params = {
    "from": settings.from_email,
    "to": ["outreach@longevityintime.org"],
    "subject": "✅ CureForge Outreach Agent — Test Email",
    "html": """
    <h2>🧬 CureForge Outreach System — Test Successful</h2>
    <p>This is a test email confirming that the automated investor outreach system is live and working.</p>
    <hr>
    <p><strong>System Status:</strong> ✅ Online</p>
    <p><strong>From:</strong> outreach@longevityintime.org</p>
    <p><strong>Next Step:</strong> Investor outreach to 70+ VC funds from the LinkedIn list is ready to launch.</p>
    <br>
    <p>— CureForge Autonomous Research Institute</p>
    """
}

print(f"Sending test email from {settings.from_email}...")
try:
    response = resend.Emails.send(params)
    print(f"✅ SUCCESS! Email sent. ID: {response['id']}")
except Exception as e:
    print(f"❌ Failed: {e}")
