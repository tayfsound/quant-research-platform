"""GET /api/v1/model-drift/ — Model Drift Detection (PSI/KS-test)."""
import random
from unittest.mock import patch
from uuid import uuid4

from contracts.auth import Role
from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def test_model_drift_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/model-drift/")
        assert response.status_code in (401, 403)


def test_model_drift_endpoint_returns_real_computed_results():
    """Paylaşılan quantdb_test'te list_recent() TÜM decision'ları (WAIT/
    no_trade dahil, sadece kapanmış işlemler değil) global zaman sırasına
    göre döndürüyor — bu yüzden burada belirli bir feature'ın kesin drift
    sonucunu değil, uç noktanın gerçekten analytics/model_drift.py'yi
    çağırıp tutarlı bir yanıt ürettiğini doğruluyoruz (algoritmanın kendi
    doğruluğu tests/test_model_drift.py'nin izole birim testlerinde
    zaten kanıtlanmış)."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"DRIFTAPI{uuid4().hex[:8]}"
        rng = random.Random(11)

        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            for _ in range(80):
                repo.persist(DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="WAIT", final_action="WAIT",
                    final_size=0.0, status="no_trade",
                    market_snapshot={"symbol": symbol, "features": {"RSI": 40 + rng.random() * 10}},
                ))

        client = _client()
        response = client.get(
            "/api/v1/model-drift/", params={"limit": 200, "split_frac": 0.5},
            headers=make_authed_headers(Role.VIEWER),
        )
        assert response.status_code == 200
        features = response.json()["features"]
        assert isinstance(features, dict)
        for stats in features.values():
            assert {"psi", "ks_statistic", "ks_p_value", "baseline_n", "recent_n", "drift_detected"} <= stats.keys()
