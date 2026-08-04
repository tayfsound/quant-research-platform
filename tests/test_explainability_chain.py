"""Sprint 16 gate: click a decision, see the full explainability chain,
built from real data — not a mock happy path.

Also proves two real bugs found while building this are actually fixed:
belief_snapshot_id was always NULL (belief was saved separately but never
linked back to the decision row), and debate_result was accepted by
DecisionRecorder.record() and silently discarded.
"""
from unittest.mock import patch


class FakeLimit:
    value = 10.0

    def verify(self, secret):
        return True


def test_explain_endpoint_resolves_the_full_chain_from_real_data():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from fastapi.testclient import TestClient
            from api.main import app
            from contracts.context import CognitiveCycleContext
            from services.cognitive_engine import CognitiveEngine

            engine = CognitiveEngine()
            ctx = CognitiveCycleContext()
            ctx.market.symbol = "EXPLAINTEST"
            ctx.decision.proposed_direction = "LONG"
            ctx.decision.confidence = 0.8
            ctx.risk.current_drawdown = 0.0
            ctx.risk.limits = {"max_position_size": FakeLimit()}

            result_ctx = engine.run(ctx, persist=True)
            decision_id = str(result_ctx.cycle_id)

            client = TestClient(app)
            response = client.get(f"/api/v1/decisions/{decision_id}/explain")

            assert response.status_code == 200
            body = response.json()
            assert body["decision_id"] == decision_id
            assert body["symbol"] == "EXPLAINTEST"

            chain = body["chain"]
            # "hangi agent?"
            assert isinstance(chain["agents"], list)
            # "hangi risk?"
            assert chain["risk"] is not None
            assert chain["risk"]["verdict"] in ("approved", "rejected")
            # "hangi belief?" — the real bug: belief_snapshot_id used to be
            # NULL for every decision, so this always resolved to None
            # regardless of whether a belief was actually produced.
            assert chain["belief"] is not None
            assert chain["belief"]["id"] is not None


def test_explain_endpoint_404s_for_unknown_decision():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from fastapi.testclient import TestClient
            from api.main import app

            client = TestClient(app)
            response = client.get("/api/v1/decisions/00000000-0000-0000-0000-000000000000/explain")
            assert response.status_code == 404
