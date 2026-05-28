from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CandidateRow(Base):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    github_handle: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, default="Software Engineer")
    level: Mapped[str] = mapped_column(String, default="senior")
    background_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confirmed_jd_id: Mapped[str | None] = mapped_column(String, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    notice_period: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_roles: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String, default="founder_added")
    state: Mapped[str] = mapped_column(String, default="NEW", index=True)
    round: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class TaskRow(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    candidate_brief: Mapped[str] = mapped_column(Text, nullable=False)
    internal_spec: Mapped[dict] = mapped_column(JSON, default=dict)
    repo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    corpus_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EvaluationRow(Base):
    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    submission_sha: Mapped[str] = mapped_column(String, nullable=False)
    dimension_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    composite: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    red_flags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    feedback_draft: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DraftEmailRow(Base):
    __tablename__ = "draft_emails"

    draft_id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    to_email: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MessageRow(Base):
    """§11 messages table — every inbound and outbound email."""
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String, nullable=False)   # "inbound" | "outbound"
    template_id: Mapped[str | None] = mapped_column(String, nullable=True)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sent_by_agent: Mapped[bool] = mapped_column(default=True)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    gmail_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TransitionRow(Base):
    """§11 transitions table — every FSM state change."""
    __tablename__ = "transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    from_state: Mapped[str] = mapped_column(String, nullable=False)
    to_state: Mapped[str] = mapped_column(String, nullable=False)
    predicate: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # "SUCCESS" | "REJECTED"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLogRow(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="recruiter")  # "admin" | "recruiter"
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
