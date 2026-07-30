"""Add outcome JSONB to decisions.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "decisions",
        sa.Column(
            "outcome",
            postgresql.JSONB(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("decisions", "outcome")
