"""add role and level to candidates

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-05-27

"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('candidates', sa.Column('role', sa.String(), nullable=True, server_default='Software Engineer'))
    op.add_column('candidates', sa.Column('level', sa.String(), nullable=True, server_default='senior'))


def downgrade() -> None:
    op.drop_column('candidates', 'level')
    op.drop_column('candidates', 'role')
