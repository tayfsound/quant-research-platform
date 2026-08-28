"""GET /api/v1/agent-pairwise-ablation — Faz 368-devam uçtan uca kablo
testleri. Gatherer'ın gerçek DB'den okuyup analytics/agent_ablation.py'nin
pairwise fonksiyonlarını doğru zincirlediğini doğrular (pure fonksiyonların
kendi mantığı tests/test_agent_ablation.py'de zaten test edildi)."""
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from contracts.agent import AgentDomain, AgentOpinion
from contracts.auth import Role
from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def _opinion(domain: str, direction: str, confidence: float) -> dict:
    """DecisionPersistor.persist() agent_opinions'ı OLDUĞU GİBİ (recalculate
    ÇAĞIRMADAN) kaydeder — effective_influence varsayılanı 0.0'dır, bu
    yüzden burada da (tests/test_agent_ablation.py::_opinion_dict ile AYNI
    şekilde) elle recalculate() çağrılmazsa TÜM oylar sıfır ağırlıklı olur
    ve belief-fusion dejenere bir sonuç üretir."""
    o = AgentOpinion(agent_id=f"{domain}_agent", domain=AgentDomain(domain), direction=direction, confidence=confidence)
    o.recalculate()
    return o.model_dump(mode="json")


def test_agent_pairwise_ablation_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/agent-pairwise-ablation/")
        assert response.status_code in (401, 403)


def test_agent_pairwise_ablation_detects_redundant_substitutes_from_real_closed_trades():
    """technical + macro'nun İKİSİ DE 0.9 LONG oyladığı (tek başına hiçbiri
    pivotal değil ama ikisi birden çıkınca WAIT'e düşen) 12 gerçek kapanmış
    karar üretip, gatherer'ın bunu substitution_rate=1.0 olarak doğru
    ölçtüğünü doğrular."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"PWABL{uuid4().hex[:8]}USDT"
        now = datetime.now(UTC)

        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            for i in range(12):
                event = DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, confidence=0.6, status="open",
                    entry_price=100.0, quantity=1.0, opened_at=now,
                    agent_opinions=[
                        _opinion("technical", "LONG", 0.9),
                        _opinion("macro", "LONG", 0.9),
                    ],
                )
                repo.persist(event)
                repo.close_position(decision_id=str(event.id), exit_price=101.0, pnl=1.0, closed_at=now)

        client = _client()
        response = client.get("/api/v1/agent-pairwise-ablation/", headers=make_authed_headers(Role.VIEWER))
        assert response.status_code == 200
        by_pair = response.json()["result"]["by_pair"]
        # Diğer canlı/gerçek işlemler de aynı çifti üretebileceğinden tam
        # eşitlik yerine EN AZ 12 ortak-oy ve substitution_rate>0 kontrol
        # ediliyor (gerçek prod verisiyle çalışan uçtan uca bir test).
        assert "macro|technical" in by_pair
        stats = by_pair["macro|technical"]
        assert stats["n_both_voted"] >= 12
        assert stats["redundant_substitutes_count"] >= 12
        assert stats["substitution_rate"] > 0


def test_agent_pairwise_ablation_reports_requires_auth():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        response = client.get("/api/v1/agent-pairwise-ablation/reports")
        assert response.status_code in (401, 403)


def test_agent_pairwise_ablation_reports_returns_saved_snapshots():
    from contracts.agent_pairwise_ablation_report import AgentPairwiseAblationReport
    from database.repositories.agent_pairwise_ablation_report_repository import (
        AgentPairwiseAblationReportRepository,
    )

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        with SessionFactory.get_session() as session:
            report = AgentPairwiseAblationReport(
                result={"by_pair": {"macro|technical": {"n_both_voted": 5}}, "n_decisions_analyzed": 100}
            )
            AgentPairwiseAblationReportRepository(session).save(report)

        client = _client()
        response = client.get(
            "/api/v1/agent-pairwise-ablation/reports", params={"limit": 5}, headers=make_authed_headers(Role.VIEWER)
        )
        assert response.status_code == 200
        reports = response.json()["reports"]
        assert any(r["id"] == str(report.id) for r in reports)
