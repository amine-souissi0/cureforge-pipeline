#!/usr/bin/env python3
"""
Automate Gmail Pub/Sub push notification setup.

What this does:
    1. Creates a Cloud Pub/Sub topic (if not exists)
    2. Grants Gmail permission to publish to it
    3. Creates a push subscription pointing at your webhook endpoint
    4. Calls Gmail users.watch() to start push notifications

Usage:
    python scripts/setup_pubsub.py

Prerequisites:
    - Gmail OAuth complete (run setup_gmail_oauth.py first)
    - Google Cloud project with Pub/Sub API enabled
    - .env file with WEBHOOK_URL set (your deployed domain)

Environment variables used:
    GCP_PROJECT_ID       Your Google Cloud project ID
    WEBHOOK_URL          e.g. https://api.yourdomain.com
    API_KEY              Your pipeline API key (sent as X-API-Key header)
    GOOGLE_TOKEN_FILE    Path to gmail token (default: config/google_token.json)
    GMAIL_TOKEN_JSON     Token JSON string (overrides file, for Docker/prod)
    PUBSUB_TOPIC_ID      Topic name (default: gmail-push)
    PUBSUB_SUB_ID        Subscription name (default: gmail-push-sub)
"""
import json
import os
import sys


def load_env() -> None:
    """Load .env if present."""
    if os.path.exists(".env"):
        with open(".env") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


def require(key: str) -> str:
    val = os.environ.get(key, "")
    if not val:
        print(f"✗ Missing required env var: {key}")
        sys.exit(1)
    return val


def get_gmail_credentials():
    token_json = os.environ.get("GMAIL_TOKEN_JSON", "")
    token_file = os.environ.get("GOOGLE_TOKEN_FILE", "config/google_token.json")
    scopes = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
    ]
    try:
        from google.oauth2.credentials import Credentials
        if token_json:
            return Credentials.from_authorized_user_info(json.loads(token_json), scopes)
        if os.path.exists(token_file):
            return Credentials.from_authorized_user_file(token_file, scopes)
    except Exception as e:
        print(f"✗ Failed to load Gmail credentials: {e}")
        sys.exit(1)
    print("✗ No Gmail credentials found. Run setup_gmail_oauth.py first.")
    sys.exit(1)


def main() -> None:
    load_env()

    print("\n=== CureForge — Pub/Sub + Gmail Watch Setup ===\n")

    project_id = require("GCP_PROJECT_ID")
    webhook_url = require("WEBHOOK_URL").rstrip("/")
    api_key = require("API_KEY")
    topic_id = os.environ.get("PUBSUB_TOPIC_ID", "gmail-push")
    sub_id = os.environ.get("PUBSUB_SUB_ID", "gmail-push-sub")

    topic_name = f"projects/{project_id}/topics/{topic_id}"
    sub_name = f"projects/{project_id}/subscriptions/{sub_id}"
    push_endpoint = f"{webhook_url}/candidates/webhook"
    gmail_sa = "gmail-api-push@system.gserviceaccount.com"

    try:
        from googleapiclient.discovery import build
        from google.auth import default as google_auth_default
    except ImportError:
        print("✗ Missing: pip install google-api-python-client google-auth")
        sys.exit(1)

    # Use application default credentials for Pub/Sub admin operations
    try:
        adc_creds, _ = google_auth_default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    except Exception as e:
        print(f"✗ Application Default Credentials not set up: {e}")
        print("  Run: gcloud auth application-default login")
        sys.exit(1)

    pubsub = build("pubsub", "v1", credentials=adc_creds)

    # 1. Create topic
    print(f"Creating topic: {topic_name}")
    try:
        pubsub.projects().topics().create(name=topic_name, body={}).execute()
        print("  ✓ Topic created")
    except Exception as e:
        if "already exists" in str(e).lower() or "409" in str(e):
            print("  ✓ Topic already exists")
        else:
            print(f"  ✗ Failed: {e}")
            sys.exit(1)

    # 2. Grant Gmail publish permission
    print(f"Granting gmail-api-push publish rights on topic")
    try:
        policy = pubsub.projects().topics().getIamPolicy(resource=topic_name).execute()
        bindings = policy.get("bindings", [])
        publisher_binding = next(
            (b for b in bindings if b["role"] == "roles/pubsub.publisher"), None
        )
        if publisher_binding:
            if f"serviceAccount:{gmail_sa}" not in publisher_binding.get("members", []):
                publisher_binding["members"].append(f"serviceAccount:{gmail_sa}")
        else:
            bindings.append({
                "role": "roles/pubsub.publisher",
                "members": [f"serviceAccount:{gmail_sa}"],
            })
        policy["bindings"] = bindings
        pubsub.projects().topics().setIamPolicy(
            resource=topic_name, body={"policy": policy}
        ).execute()
        print("  ✓ IAM policy updated")
    except Exception as e:
        print(f"  ✗ IAM update failed: {e}")
        sys.exit(1)

    # 3. Create push subscription
    print(f"Creating push subscription → {push_endpoint}")
    sub_body = {
        "topic": topic_name,
        "pushConfig": {
            "pushEndpoint": push_endpoint,
            "attributes": {},
            # Pub/Sub will include this header on every push request
            "oidcToken": {},
        },
    }
    # Inject the API key as a custom attribute header via URL param fallback
    # (Pub/Sub push doesn't natively support custom headers; use URL query param)
    sub_body["pushConfig"]["pushEndpoint"] = f"{push_endpoint}?api_key={api_key}"

    try:
        pubsub.projects().subscriptions().create(name=sub_name, body=sub_body).execute()
        print("  ✓ Push subscription created")
    except Exception as e:
        if "already exists" in str(e).lower() or "409" in str(e):
            print("  ✓ Subscription already exists")
        else:
            print(f"  ✗ Failed: {e}")
            sys.exit(1)

    # 4. Call Gmail users.watch()
    print("Setting up Gmail watch (push notifications)")
    try:
        gmail_creds = get_gmail_credentials()
        gmail = build("gmail", "v1", credentials=gmail_creds)
        watch_response = gmail.users().watch(
            userId="me",
            body={"labelIds": ["INBOX"], "topicName": topic_name},
        ).execute()
        history_id = watch_response.get("historyId")
        expiry = watch_response.get("expiration")
        print(f"  ✓ Watch active — historyId={history_id}, expires={expiry}")
        print(f"\n  ⚠ Gmail watches expire after ~7 days.")
        print(f"    Re-run this script weekly, or set up a Cloud Scheduler job to call:")
        print(f"    POST https://gmail.googleapis.com/gmail/v1/users/me/watch")
    except Exception as e:
        print(f"  ✗ Gmail watch failed: {e}")
        sys.exit(1)

    print("\n=== Setup complete ===")
    print(f"  Topic:        {topic_name}")
    print(f"  Subscription: {sub_name}")
    print(f"  Webhook:      {push_endpoint}")
    print(f"\nInbound emails to your Gmail will now route to the pipeline.\n")


if __name__ == "__main__":
    main()
