"""Semantic Search — güvenli similarity, temiz SQL."""
from database.session_factory import SessionFactory
from sqlalchemy import text
from services.embedding_service import EmbeddingService

class SemanticSearch:
    def __init__(self):
        self.embedder = EmbeddingService()

    def find_similar_episodes(
        self,
        query_features: dict[str, float],
        symbol: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        query_embedding = self.embedder.encode_features(query_features, symbol or "")
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        with SessionFactory.get_session() as session:
            conditions = ["embedding IS NOT NULL"]
            params = {"embedding": embedding_str, "limit": limit}

            if symbol:
                conditions.append("symbol = :symbol")
                params["symbol"] = symbol

            where_clause = " AND ".join(conditions)
            query = f"""
                SELECT id, symbol, decision, outcome, binding_expression, lesson,
                       embedding <#> CAST(:embedding AS vector) AS distance
                FROM episodes
                WHERE {where_clause}
                ORDER BY distance
                LIMIT :limit
            """

            result = session.execute(text(query), params)
            rows = result.mappings().all()

        return [
            {
                "episode_id": str(row["id"]),
                "symbol": row["symbol"],
                "similarity": round(max(-1.0, min(1.0, float(-row["distance"]))), 4),
                "decision": row["decision"],
                "outcome": row["outcome"],
                "binding_expression": row["binding_expression"],
                "lesson": row["lesson"],
            }
            for row in rows
        ]
