"""Belief repository — Belief Persistence V3 snapshot storage."""

import warnings

from sqlalchemy import Column, Float, Integer, MetaData, String, Table, insert, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from contracts.belief import Belief


class BeliefRepository:

    def __init__(self, session):
        self.session = session

    def save_snapshot(self, belief: Belief) -> None:
        """
        Append-only Belief V3 persistence.
        Existing snapshots are never updated.
        """

        data = {
            "id": str(belief.id),
            "direction": getattr(belief, "direction", "UNKNOWN"),
            "strength": getattr(belief, "strength", 0.0),
            "uncertainty": getattr(belief, "uncertainty", 1.0),
            "entropy": getattr(belief, "entropy", 0.0),
            "information_clusters": getattr(
                belief, "information_clusters", None
            ),
            "total_opinions": getattr(
                belief, "total_opinions", None
            ),
            "cluster_disagreement": getattr(
                belief, "cluster_disagreement", None
            ),
            "cluster_balance": getattr(
                belief, "cluster_balance", None
            ),
            "crowding_penalty": getattr(
                belief, "crowding_penalty", None
            ),
            "cluster_weights": getattr(
                belief, "cluster_weights", None
            ),
            "supporting_opinions": getattr(
                belief, "supporting_opinions", None
            ),
            "opposing_opinions": getattr(
                belief, "opposing_opinions", None
            ),
            "evidence_paths": getattr(
                belief, "evidence_paths", None
            ),
            "assumptions": getattr(
                belief, "assumptions", None
            ),
            "invalidation_conditions": getattr(
                belief, "invalidation_conditions", None
            ),
            "confidence_interval": getattr(
                belief, "confidence_interval", None
            ),
            "stability": getattr(
                belief, "stability", 0.5
            ),
            "revision_count": getattr(
                belief, "revision_count", 0
            ),
        }

        self.session.execute(
            insert(
                sa_table := self._table(),
            ).values(**data),
        )

        self.session.commit()

    def _table(self):
        return Table(
            "belief_snapshots",
            MetaData(),
            Column("id", UUID(as_uuid=True), primary_key=True),
            Column("direction", String(10), nullable=False),
            Column("strength", Float(), nullable=False),
            Column("uncertainty", Float(), nullable=False),
            Column("entropy", Float(), nullable=False),
            Column("information_clusters", Integer(), nullable=True),
            Column("total_opinions", Integer(), nullable=True),
            Column("cluster_disagreement", Float(), nullable=True),
            Column("cluster_balance", Float(), nullable=True),
            Column("crowding_penalty", Float(), nullable=True),
            Column("cluster_weights", JSONB(), nullable=True),
            Column("supporting_opinions", JSONB(), nullable=True),
            Column("opposing_opinions", JSONB(), nullable=True),
            Column("evidence_paths", JSONB(), nullable=True),
            Column("assumptions", JSONB(), nullable=True),
            Column("invalidation_conditions", JSONB(), nullable=True),
            Column("confidence_interval", JSONB(), nullable=True),
            Column("stability", Float(), nullable=True),
            Column("revision_count", Integer(), nullable=True),
        )

    def get_latest(self, limit: int = 10) -> list[dict]:

        result = self.session.execute(
            text("""
            SELECT *
            FROM belief_snapshots
            ORDER BY timestamp DESC
            LIMIT :limit
            """),
            {"limit": limit},
        )

        return [
            dict(row)
            for row in result.mappings().all()
        ]

    def get_by_id(self, belief_id) -> dict | None:
        """Fetch one specific belief snapshot — needed to resolve a
        decision's belief_snapshot_id for the explainability chain (Sprint
        16), not just 'latest' or 'by direction'."""
        result = self.session.execute(
            text("SELECT * FROM belief_snapshots WHERE id = :id"),
            {"id": str(belief_id)},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    def get_by_direction(
        self,
        direction: str,
        limit: int = 10,
    ) -> list[dict]:

        result = self.session.execute(
            text("""
            SELECT *
            FROM belief_snapshots
            WHERE direction = :direction
            ORDER BY timestamp DESC
            LIMIT :limit
            """),
            {
                "direction": direction,
                "limit": limit,
            },
        )

        return [
            dict(row)
            for row in result.mappings().all()
        ]

    def save(self, belief: Belief):
        warnings.warn(
            "save() deprecated. Use save_snapshot().",
            DeprecationWarning,
        )
        return self.save_snapshot(belief)

    def get_by_expression(
        self,
        expression: str
    ) -> dict | None:

        warnings.warn(
            "get_by_expression() deprecated.",
            DeprecationWarning,
        )

        rows = self.get_latest(limit=1)
        return rows[0] if rows else None

    def all(self) -> list[dict]:

        warnings.warn(
            "all() deprecated. Use get_latest().",
            DeprecationWarning,
        )

        return self.get_latest(limit=1000)
