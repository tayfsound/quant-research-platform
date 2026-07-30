"""reconcile initial memory schema

Revision ID: f8fa21f0e94a
Revises: 0002
Create Date: 2026-07-23
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "f8fa21f0e94a"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Existing AI memory schema reconciliation.

    Tables already exist from legacy initialization:
    - observations
    - episodes
    - beliefs
    - experiments
    - lessons

    No DDL changes applied. This migration records alignment
    between existing database state and Alembic history.
    """
    pass


def downgrade() -> None:
    """
    Intentionally empty.

    Cognitive memory tables contain persistent data and
    should never be dropped automatically.
    """
    pass
