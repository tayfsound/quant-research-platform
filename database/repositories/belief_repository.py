"""Belief repository — legacy schema uyumluluğu."""

from sqlalchemy import text
from contracts.belief import Belief


class BeliefRepository:

    def __init__(self, session):
        self.session = session


    def save(self, belief: Belief):

        expression = getattr(
            belief,
            "expression",
            ""
        )

        if expression is None:
            expression = ""


        data = {
            "id": str(belief.id),
            "expression": expression,
            "confidence": getattr(
                belief,
                "strength",
                0.0
            ),
            "evidence_count": len(
                getattr(
                    belief,
                    "evidence_paths",
                    []
                )
            ),
        }


        self.session.execute(
            text("""
            INSERT INTO beliefs (
                id,
                expression,
                confidence,
                evidence_count
            )
            VALUES (
                :id,
                :expression,
                :confidence,
                :evidence_count
            )
            ON CONFLICT (expression)
            DO UPDATE SET
                confidence = EXCLUDED.confidence,
                evidence_count = EXCLUDED.evidence_count,
                updated_at = NOW()
            """),
            data,
        )

        self.session.commit()


    def get_by_expression(self, expression: str) -> dict | None:

        result = self.session.execute(
            text("""
            SELECT *
            FROM beliefs
            WHERE expression = :expression
            """),
            {
                "expression": expression
            },
        )

        row = result.mappings().first()

        return dict(row) if row else None


    def all(self) -> list[dict]:

        result = self.session.execute(
            text("""
            SELECT *
            FROM beliefs
            ORDER BY updated_at DESC
            """)
        )

        return [
            dict(row)
            for row in result.mappings().all()
        ]
