"""Faz 166: create experiment_registry table.

This table was referenced by faz161's create_hypertable('experiment_registry', ...)
and written to (silently, inside a try/except) since Faz 159's RecordingStage
binding, but no migration ever created it — every write has been failing and
being swallowed. This closes that gap.

Revision ID: faz166
Revises: faz165
Create Date: 2026-08-04
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz166"
down_revision = "faz165"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiment_registry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("git_sha", sa.String(40), nullable=False),
        sa.Column("risk_limits_version", sa.Integer(), nullable=False),
        sa.Column("feature_schema_id", sa.String(64), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("decision_ids", postgresql.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("experiment_registry")
