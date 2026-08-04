"""Faz 165: weight_approvals TTL + decided_at columns.

Branches off 0005 (not faz161) deliberately: faz161's create_hypertable() calls
fail locally against non-empty tables (needs migrate_data=>true, a separate
data-migration decision — see AI_MEMORY_SYSTEM/CURRENT_STATE.md known gaps).
Alembic history still has two heads (0005-branch, faz161) until that is resolved.

Revision ID: faz165
Revises: 0005
Create Date: 2026-08-04
"""
import sqlalchemy as sa
from alembic import op

revision = "faz165"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("weight_approvals", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.add_column("weight_approvals", sa.Column("decided_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("weight_approvals", "decided_at")
    op.drop_column("weight_approvals", "expires_at")
