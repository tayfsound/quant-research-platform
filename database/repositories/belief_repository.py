"""Belief repository — Belief Persistence V3 snapshot storage."""

import json
import warnings

from sqlalchemy import text

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
            "cluster_weights": json.dumps(
                getattr(belief, "cluster_weights", {})
            ),
            "supporting_opinions": json.dumps(
                getattr(belief, "supporting_opinions", [])
            ),
            "opposing_opinions": json.dumps(
                getattr(belief, "opposing_opinions", [])
            ),
            "evidence_paths": json.dumps(
                getattr(belief, "evidence_paths", [])
            ),
            "assumptions": json.dumps(
                getattr(belief, "assumptions", [])
            ),
            "invalidation_conditions": json.dumps(
                getattr(belief, "invalidation_conditions", [])
            ),
            "confidence_interval": json.dumps(
                list(getattr(
                    belief,
                    "confidence_interval",
                    (0.0, 0.0),
                ))
            ),
            "stability": getattr(
                belief, "stability", 0.5
            ),
            "revision_count": getattr(
                belief, "revision_count", 0
            ),
        }

        self.session.execute(
            text("""
            INSERT INTO belief_snapshots (
                id,
                direction,
                strength,
                uncertainty,
                entropy,
                information_clusters,
                total_opinions,
                cluster_disagreement,
                cluster_balance,
                crowding_penalty,
                cluster_weights,
                supporting_opinions,
                opposing_opinions,
                evidence_paths,
                assumptions,
                invalidation_conditions,
                confidence_interval,
                stability,
                revision_count
            )
            VALUES (
                :id,
                :direction,
                :strength,
                :uncertainty,
                :entropy,
                :information_clusters,
                :total_opinions,
                :cluster_disagreement,
                :cluster_balance,
                :crowding_penalty,
                :cluster_weights,
                :supporting_opinions,
                :opposing_opinions,
                :evidence_paths,
                :assumptions,
                :invalidation_conditions,
                :confidence_interval,
                :stability,
                :revision_count
            )
            """),
            data,
        )

        self.session.commit()

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
