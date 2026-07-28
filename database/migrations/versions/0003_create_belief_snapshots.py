"""create belief_snapshots table

Revision ID: 0003
Revises: f8fa21f0e94a
Create Date: 2026-07-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "f8fa21f0e94a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "belief_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "direction",
            sa.String(10),
            nullable=False,
        ),
        sa.Column(
            "strength",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "uncertainty",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "entropy",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "information_clusters",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "total_opinions",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "cluster_disagreement",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "cluster_balance",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "crowding_penalty",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "cluster_weights",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column(
            "supporting_opinions",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column(
            "opposing_opinions",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column(
            "evidence_paths",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column(
            "assumptions",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column(
            "invalidation_conditions",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column(
            "confidence_interval",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column(
            "stability",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "revision_count",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_belief_snapshots_timestamp",
        "belief_snapshots",
        ["timestamp"],
    )

    op.create_index(
        "ix_belief_snapshots_direction",
        "belief_snapshots",
        ["direction"],
    )

    op.create_index(
        "ix_belief_snapshots_timestamp_direction",
        "belief_snapshots",
        ["timestamp", "direction"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_belief_snapshots_timestamp_direction",
        table_name="belief_snapshots",
    )
    op.drop_index(
        "ix_belief_snapshots_direction",
        table_name="belief_snapshots",
    )
    op.drop_index(
        "ix_belief_snapshots_timestamp",
        table_name="belief_snapshots",
    )
    op.drop_table("belief_snapshots")
