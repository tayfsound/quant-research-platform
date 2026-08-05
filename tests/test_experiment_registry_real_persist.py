"""ExperimentRegistry: the experiment_registry table never existed in any migration,
so every save() since Faz 159 silently failed inside RecordingStage's bare
except-pass. This proves a real cycle now genuinely persists a row, and the
list API surfaces it with a real (non-"unknown") git_sha."""
from unittest.mock import patch


class FakeLimit:
    value = 10.0

    def verify(self, secret):
        return True


def test_real_cycle_persists_experiment_registry_row_and_api_lists_it():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from fastapi.testclient import TestClient
            from api.main import app
            from services.cognitive_engine import CognitiveEngine
            from contracts.context import CognitiveCycleContext

            engine = CognitiveEngine()
            ctx = CognitiveCycleContext()
            ctx.market.symbol = "BTCUSDT"
            ctx.decision.proposed_direction = "LONG"
            ctx.decision.confidence = 0.8
            ctx.risk.current_drawdown = 0.0
            ctx.risk.limits = {"max_position_size": FakeLimit()}
            engine.run(ctx, persist=True)

            from contracts.auth import Role
            from tests.auth_helpers import make_authed_headers

            client = TestClient(app)
            response = client.get(
                "/api/v1/experiments/?limit=50",
                headers=make_authed_headers(Role.VIEWER),
            )

            assert response.status_code == 200
            experiments = response.json()["experiments"]
            assert len(experiments) >= 1
            assert all(e["git_sha"] != "unknown" and e["git_sha"] != "" for e in experiments)
