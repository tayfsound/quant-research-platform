"""Faz 182: create weight_approvals table.

Discovered while running the full migration chain against a genuinely
empty scratch database (docker run timescale/timescaledb, no data) —
faz165_weight_approval_ttl.py ALTERs this table to add expires_at/decided_at,
but no migration anywhere ever CREATEs it. It only worked on the real dev
DB because the table was created out-of-band at some point (same root cause
as known gap #13, which was the identical bug for experiment_registry).
Inserted between 0005 and faz165 (which now depends on this instead of 0005
directly) since faz165's ALTER TABLE requires the table to already exist.

Revision ID: faz165_base
Revises: 0005
Create Date: 2026-08-04
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz165_base"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weight_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("proposed_weights", postgresql.JSON(), nullable=True),
        sa.Column("previous_weights", postgresql.JSON(), nullable=True),
        sa.Column("max_delta", sa.Float(), nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("approved_by", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("weight_approvals")
