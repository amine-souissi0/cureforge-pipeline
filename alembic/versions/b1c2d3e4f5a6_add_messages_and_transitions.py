"""add_messages_and_transitions

Revision ID: b1c2d3e4f5a6
Revises: 402d5e66fcbf
Create Date: 2026-05-27

"""
from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "402d5e66fcbf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("candidate_id", sa.String, nullable=False, index=True),
        sa.Column("direction", sa.String, nullable=False),
        sa.Column("template_id", sa.String, nullable=True),
        sa.Column("subject", sa.String, nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("sent_by_agent", sa.Boolean, default=True),
        sa.Column("approved_by", sa.String, nullable=True),
        sa.Column("gmail_id", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "transitions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.String, nullable=False, index=True),
        sa.Column("from_state", sa.String, nullable=False),
        sa.Column("to_state", sa.String, nullable=False),
        sa.Column("predicate", sa.String, nullable=False),
        sa.Column("actor", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("transitions")
    op.drop_table("messages")
