"""GET /api/v1/historical-analogs — FIL Faz D. Agent Combination
Reliability'nin (services/agent_combination_reliability_gatherer.py)
"hangi ajan İKİLİLERİ birlikte anlaştı" sorusunun üçüncü eksenli hâli:
"hangi ajan kombinasyonu + hangi rejimde ne olmuş" — AYNI test deseni
(tests/test_agent_combination_reliability_wiring.py)."""
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_historical_analogs_requires_auth():
    client = _client()
    response = client.get("/api/v1/historical-analogs/")
    assert response.status_code in (401, 403)


def test_historical_analogs_returns_real_shape_and_is_json_serializable():
    client = _client()
    response = client.get("/api/v1/historical-analogs/", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    result = response.json()["result"]
    assert "analogs" in result
    assert "baseline_win_rate" in result
    assert "n_trades" in result
    for analog in result["analogs"]:
        assert isinstance(analog["domains"], list)
        assert len(analog["domains"]) == analog["combination_size"]
        assert analog["direction"] in ("LONG", "SHORT")
        assert isinstance(analog["market_regime"], str)
        assert 0.0 <= analog["win_rate"] <= 1.0
        assert isinstance(analog["fdr_significant"], bool)
        assert isinstance(analog["gate_eligible"], bool)
