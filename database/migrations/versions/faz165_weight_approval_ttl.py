"""Faz 165: weight_approvals TTL + decided_at columns.

Depends on faz165_base (which creates the table this ALTERs) rather than
0005 directly. Originally branched off 0005 to avoid faz161's
create_hypertable() calls, which fail locally against non-empty tables
(needs migrate_data=>true) — that reasoning is now moot, faz169 merges the
faz161 branch back in and both are verified to apply cleanly on an empty DB.

Revision ID: faz165
Revises: faz165_base
Create Date: 2026-08-04
"""
import sqlalchemy as sa
from alembic import op

revision = "faz165"
down_revision = "faz165_base"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("weight_approvals", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.add_column("weight_approvals", sa.Column("decided_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("weight_approvals", "decided_at")
    op.drop_column("weight_approvals", "expires_at")
