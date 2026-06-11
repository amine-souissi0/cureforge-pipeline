"""
Tests for agents/email_agent.py

All Resend SDK calls and database sessions are mocked so no real network
traffic or file I/O occurs.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from agents.email_agent import send_and_record, send_email


class TestSendEmail:
    def test_returns_message_id(self):
        """send_email should return the ID from Resend's response."""
        mock_response = {"id": "msg_abc123"}
        with patch("agents.email_agent.resend.Emails.send", return_value=mock_response) as mock_send:
            result = send_email("bob@example.com", "Hello", "<p>Hi</p>")

        assert result == "msg_abc123"
        mock_send.assert_called_once()

    def test_sends_correct_payload(self):
        """send_email must pass from/to/subject/html to Resend."""
        mock_response = {"id": "msg_xyz"}
        with patch("agents.email_agent.resend.Emails.send", return_value=mock_response) as mock_send:
            send_email(
                "recipient@example.com",
                "Test Subject",
                "<h1>Body</h1>",
                from_email="custom@longevityintime.org",
            )

        call_params = mock_send.call_args[0][0]
        assert call_params["to"] == ["recipient@example.com"]
        assert call_params["subject"] == "Test Subject"
        assert call_params["html"] == "<h1>Body</h1>"
        assert call_params["from"] == "custom@longevityintime.org"

    def test_propagates_resend_exception(self):
        """send_email should not swallow Resend SDK errors."""
        with patch("agents.email_agent.resend.Emails.send", side_effect=Exception("API error")):
            with pytest.raises(Exception, match="API error"):
                send_email("x@example.com", "Subj", "<p>body</p>")


class TestSendAndRecord:
    def test_creates_new_db_record_on_success(self, db_session, sample_investor):
        """send_and_record should insert an OutreachRecord when none exists."""
        mock_response = {"id": "msg_new_001"}

        with patch("agents.email_agent.resend.Emails.send", return_value=mock_response), \
             patch("agents.email_agent.SessionLocal", return_value=db_session):
            result = send_and_record(sample_investor, "Subject", "<p>html</p>")

        assert result == "msg_new_001"

        from models.database import OutreachRecord
        record = db_session.query(OutreachRecord).filter_by(email=sample_investor["email"]).first()
        assert record is not None
        assert record.message_id == "msg_new_001"
        assert record.sent_at is not None

    def test_updates_existing_db_record(self, db_session, seeded_record, sample_investor):
        """send_and_record should update an existing record rather than duplicate it."""
        mock_response = {"id": "msg_update_002"}

        with patch("agents.email_agent.resend.Emails.send", return_value=mock_response), \
             patch("agents.email_agent.SessionLocal", return_value=db_session):
            result = send_and_record(sample_investor, "Subject", "<p>html</p>")

        assert result == "msg_update_002"

        from models.database import OutreachRecord
        records = db_session.query(OutreachRecord).filter_by(email=sample_investor["email"]).all()
        assert len(records) == 1
        assert records[0].message_id == "msg_update_002"

    def test_returns_none_on_send_failure(self, db_session, sample_investor):
        """send_and_record should return None and not crash when Resend fails."""
        with patch("agents.email_agent.resend.Emails.send", side_effect=Exception("send error")), \
             patch("agents.email_agent.SessionLocal", return_value=db_session):
            result = send_and_record(sample_investor, "Subj", "<p>body</p>")

        assert result is None
