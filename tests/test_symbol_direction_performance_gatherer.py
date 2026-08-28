"""services/symbol_direction_performance_gatherer.py — kullanıcı bulgusu
(Grok raporu doğrulaması): council SL zararları belirli sembol×yön
hücrelerinde sistematik olarak yoğunlaşıyor."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.symbol_direction_performance_gatherer import gather_symbol_direction_performance


def _persist_closed_trade(symbol: str, direction: str, pnl: float, closed_at: datetime) -> None:
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        event = DecisionEvent(
            id=uuid4(),
            symbol=symbol,
            proposed_direction=direction,
            final_action=direction,
            final_size=0.1,
            confidence=0.7,
            status="open",
            entry_price=100.0,
            quantity=1.0,
            opened_at=closed_at - timedelta(minutes=10),
            agent_opinions=[],
            market_snapshot={"features": {}},
        )
        persistor.persist(event)
        persistor.close_position(
            decision_id=str(event.id), exit_price=101.0, pnl=pnl, closed_at=closed_at, outcome={},
        )


def test_learns_a_real_toxic_symbol_direction():
    base_time = datetime.now(UTC) + timedelta(days=3655)
    symbol = f"TOXIC{uuid4().hex[:8]}USDT"

    try:
        for i in range(10):
            pnl = 100.0 if i < 3 else -200.0  # 3 kazandı, 7 kaybetti -> %30 kazanma
            _persist_closed_trade(symbol, "LONG", pnl, closed_at=base_time - timedelta(hours=i))

        result = gather_symbol_direction_performance()
        key = f"{symbol}_LONG"
        assert key in result["by_symbol_direction"]
        entry = result["by_symbol_direction"][key]
        assert entry["sample_size"] == 10
        assert abs(entry["win_rate"] - 0.3) < 1e-9
        assert entry["total_pnl"] < 0
    finally:
        with SessionFactory.get_session() as session:
            from sqlalchemy import text
            session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
            session.commit()
