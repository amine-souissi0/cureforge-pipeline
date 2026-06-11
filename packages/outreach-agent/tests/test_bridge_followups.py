from datetime import datetime, timedelta
from unittest.mock import patch

from agents.bridge import queue_drafted_letters, send_queued_drafts
from agents.followup_agent import due_follow_up_stage, run_due_follow_ups
from models.database import OutreachRecord, ReplyStatus


def test_bridge_queues_drafted_letter(db_session, monkeypatch):
    monkeypatch.setattr("agents.bridge.SessionLocal", lambda: db_session)
    monkeypatch.setattr("agents.bridge.init_db", lambda: None)

    result = queue_drafted_letters(
        [
            {
                "recipient_org": "Example Capital",
                "recipient_email": "partner@example.com",
                "subject": "CureForge AI opportunity",
                "body": "Hello from the news agent",
                "source_post_url": "https://example.com/news",
            }
        ],
        check_dns=False,
    )

    assert result.queued == 1
    record = db_session.query(OutreachRecord).filter_by(email="partner@example.com").first()
    assert record is not None
    assert record.pipeline_status == "drafted"
    assert record.drafted_subject == "CureForge AI opportunity"
    assert record.source_post_url == "https://example.com/news"


def test_send_queued_drafts_uses_existing_draft(db_session, monkeypatch):
    record = OutreachRecord(
        name="Example Capital",
        email="partner@example.com",
        firm="Example Capital",
        focus_area="longevity",
        drafted_subject="Subject",
        drafted_body="Plain text body",
        pipeline_status="drafted",
    )
    db_session.add(record)
    db_session.commit()
    record_id = record.id

    monkeypatch.setattr("agents.bridge.SessionLocal", lambda: db_session)
    monkeypatch.setattr("agents.bridge.init_db", lambda: None)

    with patch("agents.bridge.send_and_record", return_value="msg_123") as mock_send:
        result = send_queued_drafts()

    assert result.sent == 1
    assert mock_send.call_args[0][1] == "Subject"


def test_due_follow_up_stage_day_3_and_day_7():
    now = datetime.utcnow()
    record = OutreachRecord(
        name="A",
        email="a@example.com",
        sent_at=now - timedelta(days=3, minutes=1),
        reply_status=ReplyStatus.pending,
        follow_up_stage=0,
    )
    assert due_follow_up_stage(record, now) == 1

    record.follow_up_stage = 1
    record.sent_at = now - timedelta(days=7, minutes=1)
    assert due_follow_up_stage(record, now) == 2


def test_followups_skip_replied_records():
    now = datetime.utcnow()
    record = OutreachRecord(
        name="A",
        email="a@example.com",
        sent_at=now - timedelta(days=10),
        reply_status=ReplyStatus.interested,
        follow_up_stage=0,
    )
    assert due_follow_up_stage(record, now) is None


def test_run_due_followups_updates_record(db_session, monkeypatch):
    record = OutreachRecord(
        name="Alice",
        email="alice@example.com",
        firm="Alpha Capital",
        focus_area="longevity",
        drafted_subject="Original subject",
        sent_at=datetime.utcnow() - timedelta(days=4),
        reply_status=ReplyStatus.pending,
        follow_up_stage=0,
        pipeline_status="sent",
    )
    db_session.add(record)
    db_session.commit()
    record_id = record.id

    monkeypatch.setattr("agents.followup_agent.SessionLocal", lambda: db_session)
    monkeypatch.setattr("agents.followup_agent.init_db", lambda: None)

    with patch("agents.followup_agent.send_email", return_value="fu_1") as mock_send:
        result = run_due_follow_ups()

    assert result.due == 1
    assert result.sent == 1
    assert mock_send.call_args[0][0] == "alice@example.com"
    updated = db_session.get(OutreachRecord, record_id)
    assert updated.follow_up_stage == 1
    assert updated.last_follow_up_at is not None
    assert updated.pipeline_status == "followed_up"
