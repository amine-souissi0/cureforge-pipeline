"""add location, notice_period, preferred_roles to candidates

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-28

"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('candidates', sa.Column('location', sa.String(), nullable=True))
    op.add_column('candidates', sa.Column('notice_period', sa.String(), nullable=True))
    op.add_column('candidates', sa.Column('preferred_roles', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('candidates', 'preferred_roles')
    op.drop_column('candidates', 'notice_period')
    op.drop_column('candidates', 'location')
