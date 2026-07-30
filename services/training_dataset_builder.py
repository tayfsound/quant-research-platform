"""Training dataset builder — Phase 171."""

import json

from sqlalchemy import text

from database.session_factory import SessionFactory


class TrainingDatasetBuilder:

    def build(self, output_path="training_data.jsonl"):
        with SessionFactory.get_session() as session:
            rows = session.execute(
                text("""
                    SELECT *
                    FROM decisions
                    WHERE status = 'completed'
                    ORDER BY timestamp ASC
                """)
            ).mappings().all()

        with open(output_path, "w") as f:
            for row in rows:
                sample = {
                    "decision_id": str(row["id"]),
                    "symbol": row["symbol"],
                    "direction": row["direction"],
                    "size": row["size"],
                    "confidence": row["confidence"],
                    "agents": row["agent_contributions"],
                    "outcome": row["outcome"],
                    "label": 1 if (row["pnl"] or 0) > 0 else 0,
                }

                f.write(json.dumps(sample, default=str) + "\n")

        return len(rows)
