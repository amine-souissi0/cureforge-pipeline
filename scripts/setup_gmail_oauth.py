#!/usr/bin/env python3
"""
Run the Gmail OAuth2 flow in the terminal.

Usage:
    python scripts/setup_gmail_oauth.py

Prerequisites:
    1. Go to console.cloud.google.com → APIs & Services → Credentials
    2. Create an OAuth 2.0 Client ID (Desktop app type)
    3. Download the JSON and save as config/google_credentials.json
    4. Enable the Gmail API in your project

After running this script:
    - config/google_token.json is written (used by the app locally)
    - The GMAIL_TOKEN_JSON value is printed — paste it into .env for Docker/prod
"""
import json
import os
import sys

CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE", "config/google_credentials.json")
TOKEN_FILE = os.environ.get("GOOGLE_TOKEN_FILE", "config/google_token.json")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


def main() -> None:
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"\n✗ Credentials file not found: {CREDENTIALS_FILE}")
        print("  1. Visit https://console.cloud.google.com/apis/credentials")
        print("  2. Create an OAuth 2.0 Client ID (Desktop app)")
        print("  3. Download the JSON file")
        print(f"  4. Save it as {CREDENTIALS_FILE}")
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("✗ Missing dependency: pip install google-auth-oauthlib")
        sys.exit(1)

    print("\n=== Gmail OAuth Setup ===\n")
    print("A browser window will open for Google authorization.")
    print("If running headless, the URL will be printed — open it on any machine.\n")

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)

    # run_local_server opens a browser; falls back to console if headless
    try:
        creds = flow.run_local_server(port=0, open_browser=True)
    except Exception:
        # Headless fallback: print URL, accept code from stdin
        flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        print(f"Open this URL in a browser:\n\n  {auth_url}\n")
        code = input("Paste the authorization code: ").strip()
        flow.fetch_token(code=code)
        creds = flow.credentials

    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    token_json = creds.to_json()

    with open(TOKEN_FILE, "w") as f:
        f.write(token_json)

    print(f"\n✓ Token written to {TOKEN_FILE}")
    print("\n── For Docker / production ───────────────────────────────────────")
    print("Add this line to your .env file:\n")
    print(f"GMAIL_TOKEN_JSON={token_json}\n")

    # Verify the token works
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        verified_creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
        service = build("gmail", "v1", credentials=verified_creds)
        profile = service.users().getProfile(userId="me").execute()
        print(f"✓ Verified — authenticated as: {profile['emailAddress']}")
        print(f"\nNext step: python scripts/setup_pubsub.py\n")
    except Exception as e:
        print(f"⚠ Token saved but verification failed: {e}")


if __name__ == "__main__":
    main()
