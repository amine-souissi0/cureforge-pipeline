"""
Tests for webhook/server.py

Uses FastAPI's TestClient (httpx-based) to exercise the /webhook endpoint.
The test engine (in-memory SQLite) is wired into the webhook's SessionLocal so
each handler call gets its own session on the shared in-memory engine.
OpenAI intent parsing is mocked throughout.
"""
import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from models.database import Base, OutreachRecord, ReplyStatus


def _make_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture()
def test_session_factory(test_engine):
    """Return a session factory wired to the in-memory test engine."""
    return sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture()
def client(test_engine, test_session_factory, monkeypatch):
    """
    TestClient for the webhook app, patched to use the in-memory test DB.
    """
    monkeypatch.setattr("webhook.server.settings.webhook_secret", "test_secret")
    monkeypatch.setattr("webhook.server.SessionLocal", test_session_factory)
    monkeypatch.setattr("webhook.server.init_db", lambda: None)

    from webhook.server import app
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def seeded_email(test_session_factory):
    """Seed an OutreachRecord in the test DB and return its email address."""
    session = test_session_factory()
    try:
        record = OutreachRecord(
            name="Alice Investor",
            email="alice@example.com",
            firm="Alpha Capital",
            focus_area="longevity biotech",
        )
        session.add(record)
        session.commit()
        return record.email
    finally:
        session.close()


def _get_record(test_session_factory, email: str):
    """Helper: fetch an OutreachRecord by email in a fresh session."""
    session = test_session_factory()
    try:
        return session.query(OutreachRecord).filter_by(email=email).first()
    finally:
        session.close()


def _email_payload(sender: str = "alice@example.com", body: str = "I am interested!"):
    return {
        "type": "email.received",
        "data": {
            "from": sender,
            "text": body,
        },
    }


class TestWebhookSignatureValidation:
    def test_valid_signature_accepted(self, client):
        payload = json.dumps(_email_payload()).encode()
        sig = _make_signature("test_secret", payload)

        with patch("agents.intent_parser.parse_intent", return_value=ReplyStatus.interested):
            resp = client.post(
                "/webhook",
                content=payload,
                headers={"Content-Type": "application/json", "resend-signature": sig},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    def test_invalid_signature_rejected(self, client):
        payload = json.dumps(_email_payload()).encode()
        bad_sig = "sha256=" + "0" * 64

        resp = client.post(
            "/webhook",
            content=payload,
            headers={"Content-Type": "application/json", "resend-signature": bad_sig},
        )

        assert resp.status_code == 401

    def test_missing_signature_rejected_when_secret_set(self, client):
        payload = json.dumps(_email_payload()).encode()
        resp = client.post(
            "/webhook",
            content=payload,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401

    def test_local_dev_allows_unsigned(self, client, monkeypatch):
        monkeypatch.setattr("webhook.server.settings.webhook_secret", "")
        monkeypatch.setattr("webhook.server.settings.local_dev", True)
        payload = json.dumps(_email_payload()).encode()

        with patch("agents.intent_parser.parse_intent", return_value=ReplyStatus.interested):
            resp = client.post(
                "/webhook",
                content=payload,
                headers={"Content-Type": "application/json"},
            )

        assert resp.status_code == 200


class TestWebhookIntentProcessing:
    def test_updates_record_on_known_sender(self, client, test_session_factory, seeded_email):
        """Reply from a known sender should update OutreachRecord.reply_status."""
        payload = json.dumps(_email_payload(sender=seeded_email)).encode()
        sig = _make_signature("test_secret", payload)

        with patch("agents.intent_parser.parse_intent", return_value=ReplyStatus.interested):
            resp = client.post(
                "/webhook",
                content=payload,
                headers={"Content-Type": "application/json", "resend-signature": sig},
            )

        assert resp.status_code == 200
        assert resp.json()["queued"] is True

        record = _get_record(test_session_factory, seeded_email)
        assert record.reply_status == ReplyStatus.interested
        assert record.reply_received_at is not None

    def test_raw_reply_stored(self, client, test_session_factory, seeded_email):
        """The raw email body should be persisted on the record."""
        body = "Sounds great, let's connect next week."
        payload = json.dumps(_email_payload(sender=seeded_email, body=body)).encode()
        sig = _make_signature("test_secret", payload)

        with patch("agents.intent_parser.parse_intent", return_value=ReplyStatus.interested):
            client.post(
                "/webhook",
                content=payload,
                headers={"Content-Type": "application/json", "resend-signature": sig},
            )

        record = _get_record(test_session_factory, seeded_email)
        assert record.raw_reply == body

    def test_unknown_sender_returns_200(self, client):
        """An unmatched sender email should not crash the server."""
        payload = json.dumps(_email_payload(sender="unknown@nowhere.com")).encode()
        sig = _make_signature("test_secret", payload)

        with patch("agents.intent_parser.parse_intent", return_value=ReplyStatus.other):
            resp = client.post(
                "/webhook",
                content=payload,
                headers={"Content-Type": "application/json", "resend-signature": sig},
            )

        assert resp.status_code == 200

    def test_non_email_event_ignored(self, client):
        """Events with type != 'email.received' should return status='ignored'."""
        payload = json.dumps({"type": "email.bounced", "data": {}}).encode()
        sig = _make_signature("test_secret", payload)

        resp = client.post(
            "/webhook",
            content=payload,
            headers={"Content-Type": "application/json", "resend-signature": sig},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_missing_body_returns_422(self, client):
        """Payload without email body text should return 422."""
        payload = json.dumps(
            {"type": "email.received", "data": {"from": "x@x.com", "text": ""}}
        ).encode()
        sig = _make_signature("test_secret", payload)

        resp = client.post(
            "/webhook",
            content=payload,
            headers={"Content-Type": "application/json", "resend-signature": sig},
        )

        assert resp.status_code == 422

    def test_invalid_json_returns_400(self, client):
        """Malformed JSON body should return 400."""
        payload = b"this is not json"
        sig = _make_signature("test_secret", payload)

        resp = client.post(
            "/webhook",
            content=payload,
            headers={"Content-Type": "application/json", "resend-signature": sig},
        )

        assert resp.status_code == 400


class TestHealthEndpoint:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestTaskApi:
    def test_tasks_enqueue_and_complete(self, client, monkeypatch):
        monkeypatch.setattr("webhook.server.settings.webhook_api_key", "")
        with patch("orchestrator.router.dispatch", return_value={"opportunities": []}):
            resp = client.post(
                "/tasks",
                json={"task_type": "grant.discover", "payload": {"keywords": "aging"}},
            )
        assert resp.status_code == 202
        task_id = resp.json()["task_id"]
        status_resp = client.get(f"/tasks/{task_id}")
        assert status_resp.status_code == 200
        body = status_resp.json()
        assert body["status"] == "completed"
        assert body["result"] == {"opportunities": []}

    def test_tasks_missing_task_type(self, client, monkeypatch):
        monkeypatch.setattr("webhook.server.settings.webhook_api_key", "")
        resp = client.post("/tasks", json={"payload": {}})
        assert resp.status_code == 422

    def test_tasks_require_api_key_when_configured(self, client, monkeypatch):
        monkeypatch.setattr("webhook.server.settings.webhook_api_key", "secret-key")
        resp = client.post(
            "/tasks",
            json={"task_type": "grant.discover", "payload": {"keywords": "x"}},
        )
        assert resp.status_code == 401

        with patch("orchestrator.router.dispatch", return_value={}):
            ok = client.post(
                "/tasks",
                json={"task_type": "grant.discover", "payload": {"keywords": "x"}},
                headers={"X-Webhook-Api-Key": "secret-key"},
            )
        assert ok.status_code == 202

        task_id = ok.json()["task_id"]
        denied = client.get(f"/tasks/{task_id}")
        assert denied.status_code == 401

        snap = client.get(
            f"/tasks/{task_id}",
            headers={"X-Webhook-Api-Key": "secret-key"},
        )
        assert snap.status_code == 200
