"""Faz 268-sonrası: PositionCloser gerçekten canlı kapanışta MAE/MFE
hesaplıyor mu — backtest'te var olup canlıda hiç çağrılmayan
analytics/mae_mfe.py::compute_mae_mfe'nin ilk canlı kullanımı."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from market_data.ingestion.ohlcv import OHLCV
from services.position_closer import PositionCloser


def _bar(t_minutes: int, open_: float, high: float, low: float, close: float) -> OHLCV:
    return OHLCV(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=t_minutes),
        open=open_, high=high, low=low, close=close, volume=100.0,
    )


class _PathPriceProvider:
    """limit=1 çağrısı SADECE son bar'ı (güncel fiyat kontrolü için),
    büyük limit çağrısı TÜM gerçek yolu (MAE/MFE hesabı için) döner —
    close_due_positions'ın gerçek iki-fetch akışını taklit ediyor."""
    def __init__(self, bars: list[OHLCV]):
        self.bars = bars

    def get_ohlcv(self, symbol, timeframe, limit=1):
        if limit < len(self.bars):
            return self.bars[-limit:]
        return list(self.bars)


def _open_position(symbol: str, stop_loss_price: float, take_profit_price: float) -> DecisionEvent:
    opened_at = datetime.now(UTC) - timedelta(minutes=3)
    event = DecisionEvent(
        id=uuid4(), timestamp=opened_at, symbol=symbol,
        proposed_direction="LONG", final_action="LONG", final_size=10.0, confidence=0.7,
        status="open", entry_price=100.0, quantity=10.0, opened_at=opened_at,
        stop_loss_price=stop_loss_price, take_profit_price=take_profit_price, leverage=1.0,
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)
    return event


def test_live_close_computes_real_mae_and_mfe_matching_the_actual_bar_path():
    symbol = f"MAEMFEPOS{uuid4().hex[:8]}"
    event = _open_position(symbol, stop_loss_price=95.0, take_profit_price=110.0)

    # Gerçek yol: girişten sonra 108'e kadar yükseliyor (MFE), sonra
    # 93.5'e kadar düşüp (MAE) stop'a (95) takılıyor (son bar close=94).
    bars = [
        _bar(0, 100.0, 100.5, 99.5, 100.0),
        _bar(1, 100.0, 108.0, 99.8, 107.0),
        _bar(2, 107.0, 107.2, 93.5, 94.0),
    ]
    closer = PositionCloser(_PathPriceProvider(bars))
    with SessionFactory.get_session() as session:
        closer.close_due_positions(DecisionPersistor(session))

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))

    outcome = row["outcome"]
    assert outcome["exit_reason"] == "stop_loss"
    assert outcome["mfe_pct"] is not None and outcome["mae_pct"] is not None
    assert abs(outcome["mfe_pct"] - 0.08) < 1e-6
    assert abs(outcome["mae_pct"] - (-0.065)) < 1e-6
    # Bu spesifik senaryo tam olarak incelemenin iddia ettiği örüntü:
    # fiyat gerçekten lehte hareket etmiş (MFE) ama stop'a takılmış.
    assert outcome["mfe_pct"] > abs(outcome["mae_pct"])


def test_live_close_mae_mfe_failure_never_blocks_the_real_close():
    """Fetch başarısız olursa (mae_pct/mfe_pct None) bile GERÇEK kapanış
    işlemi engellenmemeli — fail-closed DEĞİL, sessiz-başarısız."""
    symbol = f"MAEMFEFAIL{uuid4().hex[:8]}"
    event = _open_position(symbol, stop_loss_price=95.0, take_profit_price=110.0)

    class _BrokenProvider:
        def get_ohlcv(self, symbol, timeframe, limit=1):
            if limit == 1:
                from market_data.ingestion.ohlcv import OHLCV
                now = datetime.now(UTC)
                return [OHLCV(timestamp=now, open=94.0, high=94.0, low=94.0, close=94.0, volume=1.0)]
            raise RuntimeError("network down")

    closer = PositionCloser(_BrokenProvider())
    with SessionFactory.get_session() as session:
        closer.close_due_positions(DecisionPersistor(session))

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))

    assert row["status"] == "closed"
    assert row["outcome"]["mae_pct"] is None
    assert row["outcome"]["mfe_pct"] is None
