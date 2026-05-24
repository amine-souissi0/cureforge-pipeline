"""Create initial schema for CureForge Pipeline Agent."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = 'init001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # candidates table
    op.create_table(
        'candidates',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('github_handle', sa.String(255), nullable=True),
        sa.Column('source', sa.String(50), nullable=False, default='founder_added'),
        sa.Column('state', sa.String(50), nullable=False, default='NEW'),
        sa.Column('round', sa.Integer, nullable=False, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_candidates_email', 'candidates', ['email'], unique=True)
    op.create_index('idx_candidates_state', 'candidates', ['state'])
    
    # messages table
    op.create_table(
        'messages',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('candidate_id', UUID(as_uuid=True), nullable=False),
        sa.Column('direction', sa.String(20), nullable=False, server_default='OUTBOUND'),
        sa.Column('template_id', sa.String(100), nullable=True),
        sa.Column('body', sa.Text, nullable=False),
        sa.Column('sent_by_agent', sa.Boolean, nullable=False, default=False),
        sa.Column('approved_by', sa.String(255), nullable=True),
        sa.Column('gmail_id', sa.String(255), nullable=True),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id']),
    )
    op.create_index('idx_messages_candidate_id', 'messages', ['candidate_id'])
    op.create_index('idx_messages_gmail_id', 'messages', ['gmail_id'], unique=True)
    
    # tasks table
    op.create_table(
        'tasks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('candidate_id', UUID(as_uuid=True), nullable=False),
        sa.Column('candidate_brief', sa.Text, nullable=False),
        sa.Column('internal_spec', JSONB, nullable=False),
        sa.Column('repo_url', sa.String(255), nullable=True),
        sa.Column('corpus_ref', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id']),
    )
    op.create_index('idx_tasks_candidate_id', 'tasks', ['candidate_id'])
    
    # evaluations table
    op.create_table(
        'evaluations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('candidate_id', UUID(as_uuid=True), nullable=False),
        sa.Column('round', sa.Integer, nullable=False),
        sa.Column('submission_sha', sa.String(40), nullable=False),
        sa.Column('dimension_scores', JSONB, nullable=False),
        sa.Column('composite', sa.Numeric(4, 2), nullable=False),
        sa.Column('evidence', JSONB, nullable=False),
        sa.Column('red_flags', JSONB, nullable=True),
        sa.Column('feedback_draft', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id']),
        sa.CheckConstraint('composite >= 0 AND composite <= 10'),
    )
    op.create_index('idx_evaluations_candidate_round', 'evaluations', ['candidate_id', 'round'])
    
    # transitions table (FSM history)
    op.create_table(
        'transitions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('candidate_id', UUID(as_uuid=True), nullable=False),
        sa.Column('from_state', sa.String(50), nullable=False),
        sa.Column('to_state', sa.String(50), nullable=False),
        sa.Column('predicate', sa.String(255), nullable=False),
        sa.Column('actor', sa.String(100), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id']),
    )
    op.create_index('idx_transitions_candidate_ts', 'transitions', ['candidate_id', 'ts'])
    
    # audit_log table (immutable, append-only)
    op.create_table(
        'audit_log',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('candidate_id', UUID(as_uuid=True), nullable=True),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('actor', sa.String(100), nullable=False),
        sa.Column('inputs', JSONB, nullable=True),
        sa.Column('outputs', JSONB, nullable=True),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_audit_candidate_ts', 'audit_log', ['candidate_id', 'ts'])
    op.create_index('idx_audit_event_ts', 'audit_log', ['event_type', 'ts'])


def downgrade():
    op.drop_table('audit_log')
    op.drop_table('transitions')
    op.drop_table('evaluations')
    op.drop_table('tasks')
    op.drop_table('messages')
    op.drop_table('candidates')
