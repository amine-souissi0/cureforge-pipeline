"""add candidate_profile and confirmed_jd_id

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-28

"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('candidates', sa.Column('candidate_profile', sa.JSON(), nullable=True))
    op.add_column('candidates', sa.Column('confirmed_jd_id', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('candidates', 'confirmed_jd_id')
    op.drop_column('candidates', 'candidate_profile')
