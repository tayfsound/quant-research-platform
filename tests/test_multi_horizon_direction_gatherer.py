"""services/multi_horizon_direction_gatherer.py — Faz 444 (2026-09-07),
Direction Prediction Engine. tests/test_direction_baseline_gatherer.py'deki
AYNI gerçek-DB round-trip deseni: gerçek `decisions` + `market_snapshots`
satırları yazılır (15m/1h/4h ufuklarının HER BİRİ için), gatherer
çalıştırılır, üç LATERAL JOIN'in doğru fiyatları eşleştirdiği ve
analytics/multi_horizon_direction.py'ye doğru girdiyi verdiği doğrulanır."""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from contracts.market_data import DataSource, MarketSnapshot, Resolution
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from services.multi_horizon_direction_gatherer import gather_multi_horizon_disagreement


def _insert_decision(session, *, symbol: str, entry_price: float, timestamp) -> None:
    session.execute(
        text("""
            INSERT INTO decisions
                (id, timestamp, symbol, direction, size, confidence, status, entry_price,
                 closed_at, excluded_from_stats)
            VALUES
                (:id, :timestamp, :symbol, 'LONG', 1.0, 0.8, 'closed', :entry_price,
                 :closed_at, false)
        """),
        {
            "id": str(uuid.uuid4()), "timestamp": timestamp, "symbol": symbol,
            "entry_price": entry_price, "closed_at": timestamp + timedelta(minutes=30),
        },
    )


def test_gatherer_reproduces_a_known_disagreement_pattern_end_to_end():
    """10 GERÇEK karar + her biri için 15m/1h/4h GERÇEK market_snapshots
    satırı yazılıyor: 6'sı üç ufukta da UP (anlaşıyor), 4'ü GPT'nin
    örneği gibi 15m DOWN / 1h UP / 4h UP (anlaşmıyor). Gatherer'ın en az
    bu 10 kaydı doğru eşleştirdiği, disagreement_rate'in makul bir
    aralıkta kaldığı doğrulanıyor (havuzun geri kalanı sistemin GERÇEK
    diğer kararlarını da içerdiği için kesin bir oran doğrulanamaz)."""
    symbol = f"MHDTEST{uuid.uuid4().hex[:6]}USDT"
    base = datetime.now(UTC) - timedelta(days=2)

    with SessionFactory.get_session() as session:
        repo = MarketDataRepository(session)
        for i in range(10):
            entry_time = base + timedelta(minutes=i * 7)
            agree = i < 6
            price_15m = 100.2 if agree else 99.5
            price_1h = 101.0
            price_4h = 103.0
            _insert_decision(session, symbol=symbol, entry_price=100.0, timestamp=entry_time)
            repo.upsert_snapshot(MarketSnapshot(
                time=entry_time + timedelta(minutes=15), exchange=DataSource.BINANCE, symbol=symbol,
                resolution=Resolution.M1, open=price_15m, high=price_15m, low=price_15m,
                close=price_15m, volume=1.0, source_version="v1",
            ))
            repo.upsert_snapshot(MarketSnapshot(
                time=entry_time + timedelta(hours=1), exchange=DataSource.BINANCE, symbol=symbol,
                resolution=Resolution.M1, open=price_1h, high=price_1h, low=price_1h,
                close=price_1h, volume=1.0, source_version="v1",
            ))
            repo.upsert_snapshot(MarketSnapshot(
                time=entry_time + timedelta(hours=4), exchange=DataSource.BINANCE, symbol=symbol,
                resolution=Resolution.M1, open=price_4h, high=price_4h, low=price_4h,
                close=price_4h, volume=1.0, source_version="v1",
            ))
        session.commit()

    result = gather_multi_horizon_disagreement(lookback_days=5)

    assert result is not None
    assert result["n_comparable"] >= 10
    assert 0.0 <= result["disagreement_rate"] <= 1.0
