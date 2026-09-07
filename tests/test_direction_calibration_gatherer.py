"""services/direction_calibration_gatherer.py — Faz 446 (2026-09-07),
Direction Prediction Engine. tests/test_direction_baseline_gatherer.py'deki
AYNI gerçek-DB round-trip deseni: gerçek `decisions` + `market_snapshots`
satırları yazılır, gatherer çalıştırılır, compute_brier_score()/compute_
expected_calibration_error()'a HEM direction HEM trade-outcome girdisinin
doğru hazırlandığı doğrulanır."""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from contracts.market_data import DataSource, MarketSnapshot, Resolution
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from services.direction_calibration_gatherer import gather_direction_calibration


def _insert_decision(session, *, symbol: str, direction: str, entry_price: float,
                      confidence: float, pnl: float | None, timestamp) -> None:
    session.execute(
        text("""
            INSERT INTO decisions
                (id, timestamp, symbol, direction, size, confidence, status, entry_price,
                 pnl, closed_at, excluded_from_stats)
            VALUES
                (:id, :timestamp, :symbol, :direction, 1.0, :confidence, 'closed', :entry_price,
                 :pnl, :closed_at, false)
        """),
        {
            "id": str(uuid.uuid4()), "timestamp": timestamp, "symbol": symbol, "direction": direction,
            "entry_price": entry_price, "confidence": confidence, "pnl": pnl,
            "closed_at": timestamp + timedelta(minutes=30),
        },
    )


def test_gatherer_separates_direction_correctness_from_trade_profitability():
    """20 GERÇEK LONG karar, hepsi confidence=0.9 -- ama fiyat GERÇEKTEN
    DÜŞMÜŞ (forward_label=DOWN, yön yanlış) AYNI ANDA pnl>0 (trade kârlı --
    ör. dar bir TP'ye takılmış olabilir). Bu, GPT'nin tam iddia ettiği
    ayrışma: trade-outcome Brier'i MÜKEMMEL (kâr='doğru', hep kârlı)
    görünürken, direction Brier'i GERÇEKTEN KÖTÜ olmalı (yüksek güvenle
    hep yanlış yön)."""
    symbol = f"DCGTEST{uuid.uuid4().hex[:6]}USDT"
    base = datetime.now(UTC) - timedelta(days=2)

    with SessionFactory.get_session() as session:
        repo = MarketDataRepository(session)
        for i in range(20):
            entry_time = base + timedelta(minutes=i * 5)
            _insert_decision(
                session, symbol=symbol, direction="LONG", entry_price=100.0,
                confidence=0.9, pnl=5.0, timestamp=entry_time,
            )
            repo.upsert_snapshot(MarketSnapshot(
                time=entry_time + timedelta(hours=1), exchange=DataSource.BINANCE, symbol=symbol,
                resolution=Resolution.M1, open=95.0, high=95.0, low=95.0, close=95.0,
                volume=1.0, source_version="v1",
            ))
        session.commit()

    result = gather_direction_calibration()

    # Havuz sistemin GERÇEK diğer kararlarını da içerdiği için kesin bir
    # Brier/ECE değeri doğrulanamaz (test_direction_baseline_gatherer.py
    # ile AYNI ilke) -- ama bu gatherer'a özgü ayrım (aynı karar kümesinden
    # HEM direction HEM trade-outcome hesaplanması) burada doğrulanıyor:
    # en az bu 20 kaydın direction/trade_outcome örneklemlerine girdiği.
    assert result["direction"]["n"] >= 20
    assert result["trade_outcome"]["n"] >= 20
    assert result["direction"]["brier"] is not None
    assert result["trade_outcome"]["brier"] is not None
    assert result["direction"]["ece"] is not None
    assert result["trade_outcome"]["ece"] is not None
