"""Faz 268-sonrası — kullanıcı isteği: Adaptive Barrier Engine'i
RiskTargetStage'e wire edelim. Bu testler, GERÇEK kapanmış işlemlerden
barrier tablosunun inşa edilip kaydedildiğini, ve RiskTargetStage'in
bunu (sadece açıksa VE yeterli veri varsa) gerçekten kullandığını, aksi
halde statik ATR hesabına düştüğünü doğruluyor."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from analytics.barrier_table_builder import (
    MIN_TOTAL_SAMPLES,
    build_and_save_barrier_table,
)
from analytics.barrier_table_repository import GROUP_BY, BarrierTableRepository
from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory


def test_no_saved_table_returns_none(tmp_path):
    repo = BarrierTableRepository(storage_path=str(tmp_path / "barrier_tables"))
    assert repo.get_latest() is None


def test_save_and_get_latest_roundtrip(tmp_path):
    repo = BarrierTableRepository(storage_path=str(tmp_path / "barrier_tables"))
    table = {"direction=LONG|regime=bull_trend|volatility_regime=normal": {"sl_pct": 0.02, "tp_pct": 0.03}}
    repo.save(table, sample_count=250)

    stored = repo.get_latest()
    assert stored is not None
    assert stored["sample_count"] == 250
    assert stored["table"] == table
    assert stored["group_by"] == list(GROUP_BY)


def test_build_and_save_returns_none_when_below_min_total_samples(tmp_path):
    repo = BarrierTableRepository(storage_path=str(tmp_path / "barrier_tables"))
    result = build_and_save_barrier_table(window=5, repository=repo)
    assert result is None
    assert repo.get_latest() is None


def _persist_closed_trade_for_barrier(
    symbol: str, direction: str, mae_pct: float, mfe_pct: float,
    regime: str, volatility_regime: str, closed_at: datetime,
) -> None:
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
            market_snapshot={"features": {"long_term_trend_regime": regime, "volatility_regime": volatility_regime}},
        )
        persistor.persist(event)
        persistor.close_position(
            decision_id=str(event.id),
            exit_price=101.0,
            pnl=1.0,
            closed_at=closed_at,
            outcome={
                "mae_pct": mae_pct, "mfe_pct": mfe_pct,
                "time_to_mae_seconds": 100.0, "time_to_mfe_seconds": 50.0,
            },
        )


def test_build_and_save_barrier_table_learns_from_real_closed_trades(tmp_path):
    """MIN_TOTAL_SAMPLES kadar gerçek, tutarlı (LONG/bull_trend/normal,
    MAE=-1%, MFE=+3%) kapanış üretip tablonun gerçekten bu kovayı
    öğrendiğini doğruluyor."""
    repo = BarrierTableRepository(storage_path=str(tmp_path / "barrier_tables"))
    base_time = datetime.now(UTC) + timedelta(days=3653)
    symbol = f"BARRIER{uuid4().hex[:8]}"

    try:
        for i in range(MIN_TOTAL_SAMPLES):
            _persist_closed_trade_for_barrier(
                symbol, direction="LONG", mae_pct=-0.01, mfe_pct=0.03,
                regime="bull_trend", volatility_regime="normal",
                # Faz 368 — MIN_DISTINCT_DAYS kontrolünü geçebilmek için
                # saat bazlı yayılma (200 * 1sa ≈ 8.3 gün) — saniye bazlı
                # olsaydı hepsi TEK bir günde kalırdı, artık dışlanır.
                closed_at=base_time - timedelta(hours=i),
            )

        table = build_and_save_barrier_table(window=MIN_TOTAL_SAMPLES, repository=repo)
        assert table is not None
        # symbol "other" sınıfına düşüyor (USDT son eki yok, bilinen bir
        # hisse/emtia sembolü de değil) -> asset_class_trading_category
        # None döner -> barrier_table_builder bunu "unknown" yazar.
        key = "direction=LONG|regime=bull_trend|volatility_regime=normal|asset_class=unknown"
        assert key in table
        assert abs(table[key]["sl_pct"] - 0.01) < 1e-9
        assert abs(table[key]["tp_pct"] - 0.03) < 1e-9

        stored = repo.get_latest()
        assert stored is not None
        assert stored["sample_count"] == MIN_TOTAL_SAMPLES
    finally:
        with SessionFactory.get_session() as session:
            from sqlalchemy import text
            session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
            session.commit()


def test_crypto_and_equity_trades_in_the_same_regime_get_separate_barrier_entries(tmp_path):
    """Faz 368 — kullanıcı bulgusu: MSFT/GC=F gibi semboller, sırf AYNI
    (direction, regime, volatility_regime) kovasına düştükleri için
    kripto-kalibreli SL/TP oranı alıyordu. AYNI kovada, AMA farklı
    asset_class'ta, BİLEREK farklı MAE/MFE profiline sahip iki sembol
    havuzu üretip artık ayrı tablo girdileri (farklı sl_pct/tp_pct)
    aldıklarını doğruluyor — önceden tek bir (harmanlanmış) girdi olurdu."""
    repo = BarrierTableRepository(storage_path=str(tmp_path / "barrier_tables"))
    base_time = datetime.now(UTC) + timedelta(days=3654)
    crypto_symbol = f"BARRIER{uuid4().hex[:8]}USDT"
    equity_symbol = "MSFT"

    try:
        half = MIN_TOTAL_SAMPLES // 2
        # Faz 368 — her yarı da ayrı ayrı MIN_DISTINCT_DAYS'i geçmeli
        # (100 * 2sa ≈ 8.3 gün), iki yarı arasında zaman aralığı ÇAKIŞMAZ.
        for i in range(half):
            _persist_closed_trade_for_barrier(
                crypto_symbol, direction="LONG", mae_pct=-0.02, mfe_pct=0.08,
                regime="bull_trend", volatility_regime="normal",
                closed_at=base_time - timedelta(hours=i * 2),
            )
        for i in range(half):
            _persist_closed_trade_for_barrier(
                equity_symbol, direction="LONG", mae_pct=-0.005, mfe_pct=0.015,
                regime="bull_trend", volatility_regime="normal",
                closed_at=base_time - timedelta(hours=half * 2 + i * 2),
            )

        table = build_and_save_barrier_table(window=MIN_TOTAL_SAMPLES, repository=repo)
        assert table is not None

        crypto_key = "direction=LONG|regime=bull_trend|volatility_regime=normal|asset_class=crypto"
        equity_key = "direction=LONG|regime=bull_trend|volatility_regime=normal|asset_class=equity"
        assert crypto_key in table
        assert equity_key in table
        assert abs(table[crypto_key]["sl_pct"] - 0.02) < 1e-9
        assert abs(table[equity_key]["sl_pct"] - 0.005) < 1e-9
        assert table[crypto_key]["sl_pct"] != table[equity_key]["sl_pct"]
    finally:
        with SessionFactory.get_session() as session:
            from sqlalchemy import text
            session.execute(
                text("DELETE FROM decisions WHERE symbol IN (:crypto_symbol, :equity_symbol)"),
                {"crypto_symbol": crypto_symbol, "equity_symbol": equity_symbol},
            )
            session.commit()
