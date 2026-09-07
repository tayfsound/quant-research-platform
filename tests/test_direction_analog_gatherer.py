"""services/direction_analog_gatherer.py — Faz 445 (2026-09-07), Direction
Prediction Engine. tests/test_direction_baseline_gatherer.py'deki AYNI
gerçek-DB round-trip deseni: gerçek `decisions` (agent_contributions
JSONB dahil) + `market_snapshots` satırları yazılır, gatherer çalıştırılır,
LATERAL JOIN'in doğru fiyatı bulduğu VE agreeing_domains/forward_label'ın
compute_direction_analogs()'a doğru aktarıldığı doğrulanır."""
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from contracts.agent import AgentDomain, AgentOpinion
from contracts.market_data import DataSource, MarketSnapshot, Resolution
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from services.direction_analog_gatherer import gather_direction_analogs


def _opinion_dict(domain: AgentDomain, direction: str) -> dict:
    o = AgentOpinion(domain=domain, direction=direction, confidence=0.8)
    o.recalculate()
    return o.model_dump(mode="json")


def _insert_decision(session, *, symbol: str, entry_price: float, timestamp, contributions: list[dict]) -> None:
    session.execute(
        text("""
            INSERT INTO decisions
                (id, timestamp, symbol, direction, size, confidence, status, entry_price,
                 agent_contributions, market_regime, closed_at, excluded_from_stats)
            VALUES
                (:id, :timestamp, :symbol, 'LONG', 1.0, 0.8, 'closed', :entry_price,
                 CAST(:agent_contributions AS jsonb), 'bullish_normal', :closed_at, false)
        """),
        {
            "id": str(uuid.uuid4()), "timestamp": timestamp, "symbol": symbol, "entry_price": entry_price,
            "agent_contributions": json.dumps(contributions, default=str),
            "closed_at": timestamp + timedelta(minutes=30),
        },
    )


def test_gatherer_reproduces_a_known_up_pattern_end_to_end():
    """10 GERÇEK LONG karar, hepsi technical+macro'nun AYNI yönde
    (LONG) oy verdiği -- yani agreeing_domains={'technical','macro'} --
    ve hepsinin gerçek 1sa sonraki fiyatı YÜKSELMİŞ (forward_label=UP).
    Gatherer'ın bu hücreyi doğru bulup compute_direction_analogs()'un
    'UP' sonucuna aktardığı doğrulanıyor."""
    symbol = f"DATEST{uuid.uuid4().hex[:6]}USDT"
    base = datetime.now(UTC) - timedelta(days=2)
    contributions = [
        _opinion_dict(AgentDomain.TECHNICAL, "LONG"),
        _opinion_dict(AgentDomain.MACRO, "LONG"),
        # market_state_reversing_for_decision() SADECE bu type='market_state'
        # girdisini okuyor -- eksikse reversing=None döner ve compute_
        # historical_analogs()'un fail-closed filtresi (isinstance(...,bool))
        # kaydı TAMAMEN dışlar (Faz 404'ün kasıtlı davranışı).
        {"type": "market_state", "data": {"reversing": False}},
    ]

    with SessionFactory.get_session() as session:
        repo = MarketDataRepository(session)
        for i in range(10):
            entry_time = base + timedelta(minutes=i * 5)
            _insert_decision(session, symbol=symbol, entry_price=100.0, timestamp=entry_time, contributions=contributions)
            repo.upsert_snapshot(MarketSnapshot(
                time=entry_time + timedelta(hours=1), exchange=DataSource.BINANCE, symbol=symbol,
                resolution=Resolution.M1, open=105.0, high=105.0, low=105.0, close=105.0,
                volume=1.0, source_version="v1",
            ))
        session.commit()

    result = gather_direction_analogs()

    assert set(result.keys()) >= {"UP", "DOWN", "NEUTRAL"}
    assert result["UP"]["baseline_sample_size"] > 0
    assert result["n_trades"] > 0
