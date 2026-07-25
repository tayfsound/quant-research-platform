"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'strategies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('genome', postgresql.JSONB(), nullable=False),
        sa.Column('parent_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column('generation', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'model_registry',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('model_type', sa.String(50), nullable=False),
        sa.Column('version', sa.String(50), nullable=False),
        sa.Column('hyperparameters', postgresql.JSONB(), nullable=False),
        sa.Column('metrics', postgresql.JSONB(), nullable=False),
        sa.Column('checkpoint_path', sa.Text(), nullable=False),
        sa.Column('trained_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint('model_type', 'version'),
    )

    op.create_table(
        'risk_limits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('scope', sa.String(50), nullable=False),
        sa.Column('limit_type', sa.String(50), nullable=False),
        sa.Column('value', sa.Numeric(), nullable=False),
        sa.Column('signed_hash', sa.Text(), nullable=False),
        sa.Column('effective_at', sa.TIMESTAMP(timezone=True), nullable=False),
    )

    op.create_table(
        'feature_definitions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True),
        sa.Column('version', sa.String(50), nullable=False),
        sa.Column('definition', sa.Text(), nullable=False),
        sa.Column('source', sa.String(100), nullable=False),
        sa.Column('lookback_window', sa.Interval(), nullable=True),
        sa.Column('lookforward_window', sa.Interval(), nullable=True),
        sa.Column('quality_score', sa.Float(), server_default='1.0'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'experiment_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('model_type', sa.String(50), nullable=False),
        sa.Column('hyperparameters', postgresql.JSONB(), nullable=False),
        sa.Column('metrics', postgresql.JSONB(), nullable=False),
        sa.Column('dataset_version', sa.String(100), nullable=False),
        sa.Column('feature_set_version', sa.String(100), nullable=False),
        sa.Column('model_version', sa.String(50), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('experiment_runs')
    op.drop_table('feature_definitions')
    op.drop_table('risk_limits')
    op.drop_table('model_registry')
    op.drop_table('strategies')
