"""ContextAdapter'ın bu turda eklenen 5 yeni to_*() metodu + Faz 242-243'te
eklenen to_relative_strength()."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contracts.context import CognitiveCycleContext
from services.context_adapter import ContextAdapter


def test_to_macro_explicit_override_wins_over_real_fred_fetch():
    ctx = CognitiveCycleContext(market={"raw_snapshot": {"inflation_trend": "rising"}})
    result = ContextAdapter().to_macro(ctx)
    assert result.inflation_trend == "rising"


def test_to_macro_falls_back_to_real_fred_categories_when_no_override():
    ctx = CognitiveCycleContext()
    result = ContextAdapter().to_macro(ctx)
    assert result.inflation_trend in ("rising", "falling", "stable")
    assert result.employment_trend in ("improving", "weakening", "stable")
    assert result.central_bank_bias in ("hawkish", "dovish", "neutral")
    assert result.liquidity_condition in ("loose", "tight", "neutral")


def test_to_sentiment_uses_real_fear_greed_index_for_crypto():
    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT"})
    result = ContextAdapter().to_sentiment(ctx)
    assert 0 <= result.fear_greed_index <= 100


def test_to_sentiment_defaults_to_neutral_for_non_crypto():
    ctx = CognitiveCycleContext(market={"symbol": "AAPL"})
    result = ContextAdapter().to_sentiment(ctx)
    assert result.fear_greed_index == 50.0


def test_to_sentiment_explicit_override_wins_over_real_fetch():
    ctx = CognitiveCycleContext(market={
        "symbol": "BTCUSDT",
        "raw_snapshot": {"fear_greed_index": 12.0},
    })
    result = ContextAdapter().to_sentiment(ctx)
    assert result.fear_greed_index == 12.0


def test_to_pattern_reads_raw_snapshot():
    ctx = CognitiveCycleContext(market={"raw_snapshot": {"structure_phase": "accumulation"}})
    result = ContextAdapter().to_pattern(ctx)
    assert result.structure_phase == "accumulation"


def test_to_quant_reads_raw_snapshot():
    ctx = CognitiveCycleContext(market={"raw_snapshot": {"zscore": -1.5, "hurst_exponent": 0.3}})
    result = ContextAdapter().to_quant(ctx)
    assert result.zscore == -1.5
    assert result.hurst_exponent == 0.3


def test_to_quant_defaults_regime_changepoint_to_false():
    ctx = CognitiveCycleContext()
    result = ContextAdapter().to_quant(ctx)
    assert result.regime_changepoint_detected is False


def test_to_quant_reads_regime_changepoint_from_raw_snapshot():
    ctx = CognitiveCycleContext(market={"raw_snapshot": {"regime_changepoint_detected": True}})
    result = ContextAdapter().to_quant(ctx)
    assert result.regime_changepoint_detected is True


def test_to_order_flow_defaults_when_no_db_row_and_no_override():
    ctx = CognitiveCycleContext(market={"symbol": "NEVERINGESTEDXYZ"})
    result = ContextAdapter().to_order_flow(ctx)
    assert result.bid_ask_imbalance == 0.0
    assert result.spread_bps == 0.0


def test_to_order_flow_explicit_override_wins_over_db():
    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT", "raw_snapshot": {"bid_ask_imbalance": 0.9}})
    result = ContextAdapter().to_order_flow(ctx)
    assert result.bid_ask_imbalance == 0.9


def test_to_order_flow_defaults_funding_rate_and_oi_trend_without_db_row():
    ctx = CognitiveCycleContext(market={"symbol": f"NEVERINGESTED{uuid4().hex[:6]}USDT"})
    result = ContextAdapter().to_order_flow(ctx)
    assert result.funding_rate is None
    assert result.open_interest_trend == "unknown"


def test_to_order_flow_reads_real_funding_rate_and_oi_trend_from_db():
    """Faz 247-249: gerçek DB'ye karşı — order_book_snapshots'a yazılan
    funding_rate/open_interest_trend, to_order_flow() tarafından doğru
    okunmalı."""
    from contracts.market_data import DataSource
    from database.repositories.market_data_repository import MarketDataRepository
    from database.session_factory import SessionFactory

    symbol = f"OFTEST{uuid4().hex[:6]}USDT"
    with SessionFactory.get_session() as session:
        MarketDataRepository(session).save_order_book_snapshot(
            exchange=DataSource.BINANCE, symbol=symbol, time=datetime.now(UTC),
            best_bid=100.0, best_ask=100.1, bid_volume=10.0, ask_volume=10.0,
            imbalance=0.0, spread_bps=1.0, aggressive_buy_ratio=0.5,
            funding_rate=0.0007, open_interest=12345.0, open_interest_trend="rising",
        )

    ctx = CognitiveCycleContext(market={"symbol": symbol})
    result = ContextAdapter().to_order_flow(ctx)
    assert result.funding_rate == 0.0007
    assert result.open_interest_trend == "rising"


def test_to_time_computes_real_wall_clock_fields():
    ctx = CognitiveCycleContext()
    result = ContextAdapter().to_time(ctx)
    assert result.session in ("asia", "europe", "overlap", "us")
    assert result.day_of_week in (
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
    )
    assert 0 <= result.hours_to_funding <= 8


def test_to_epistemology_full_completeness_when_all_expected_features_present():
    ctx = CognitiveCycleContext(market={
        "features": {"RSI": 50, "ema": 100, "macd": 1, "trend": "bullish", "volatility_regime": "normal"}
    })
    result = ContextAdapter().to_epistemology(ctx)
    assert result.feature_completeness == 1.0
    assert result.known_unknown_count == 0


def test_to_epistemology_partial_completeness_when_features_missing():
    ctx = CognitiveCycleContext(market={"features": {"RSI": 50}})
    result = ContextAdapter().to_epistemology(ctx)
    assert result.feature_completeness == 0.2  # 1/5 expected features present
    assert result.known_unknown_count == 4


def test_to_epistemology_data_age_reflects_ctx_timestamp():
    old_ts = datetime.now() - timedelta(seconds=120)
    ctx = CognitiveCycleContext(timestamp=old_ts)
    result = ContextAdapter().to_epistemology(ctx)
    assert result.data_age_seconds >= 100


def test_to_epistemology_reads_real_data_quality_score_from_features():
    ctx = CognitiveCycleContext(market={"features": {"data_quality_score": 0.72}})
    result = ContextAdapter().to_epistemology(ctx)
    assert result.data_quality_score == 0.72


def test_to_epistemology_defaults_data_quality_score_to_clean_when_absent():
    ctx = CognitiveCycleContext(market={"features": {}})
    result = ContextAdapter().to_epistemology(ctx)
    assert result.data_quality_score == 1.0


def test_to_relative_strength_waits_when_symbol_never_ingested():
    """Hedefin KENDİ verisi hiç yoksa (peer'ler watchlist'te veri
    biriktirmiş olsa bile — paylaşılan test DB'sinde başka testlerden
    gerçek watchlist sembolleri için satır olabilir) dürüstçe sinyal
    üretilmemeli."""
    ctx = CognitiveCycleContext(market={"symbol": f"NEVERINGESTED{uuid4().hex[:6]}USDT"})
    result = ContextAdapter().to_relative_strength(ctx)
    assert result.symbol_return_pct == 0.0
    assert result.relative_strength_pct == 0.0


def test_to_relative_strength_waits_for_non_crypto_symbol():
    ctx = CognitiveCycleContext(market={"symbol": "AAPL"})
    result = ContextAdapter().to_relative_strength(ctx)
    # AAPL market_snapshots'a hiç ingest edilmiyor (services/tasks.py::
    # ingest_candles_task sadece Binance çiftleri) — dürüstçe hesaplanamaz.
    assert result.relative_strength_pct == 0.0


def test_to_relative_strength_computes_real_divergence_against_watchlist_peers():
    """Gerçek DB'ye karşı: hedef sembol + 3 eş için gerçek, kontrollü
    market_snapshots satırları yazılıyor (watchlist geçici olarak bu
    izole sembollere çevriliyor, testten sonra eski haline döndürülüyor),
    to_relative_strength'in doğru getiri/basket ortalaması/göreli güç
    hesapladığı doğrulanıyor."""
    from contracts.market_data import DataSource, MarketSnapshot, Resolution
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.repositories.market_data_repository import MarketDataRepository
    from database.session_factory import SessionFactory

    target = f"RSTGT{uuid4().hex[:6]}USDT"
    peers = [f"RSPEER{i}{uuid4().hex[:6]}USDT" for i in range(3)]
    peer_returns = [0.0, 0.02, -0.02]  # basket ortalaması = 0.0

    base = datetime.now(UTC).replace(microsecond=0)

    with SessionFactory.get_session() as session:
        settings_repo = AppSettingsRepository(session)
        original_watchlist = settings_repo.get("watchlist")
        repo = MarketDataRepository(session)

        def _write(sym: str, start_close: float, end_close: float) -> None:
            repo.upsert_snapshot(MarketSnapshot(
                time=base, exchange=DataSource.BINANCE, symbol=sym, resolution=Resolution.M1,
                open=start_close, high=max(start_close, end_close), low=min(start_close, end_close),
                close=start_close, volume=1.0, source_version="test",
            ))
            repo.upsert_snapshot(MarketSnapshot(
                time=base + timedelta(minutes=1), exchange=DataSource.BINANCE, symbol=sym,
                resolution=Resolution.M1, open=end_close, high=max(start_close, end_close),
                low=min(start_close, end_close), close=end_close, volume=1.0, source_version="test",
            ))

        _write(target, 100.0, 110.0)  # +%10
        for peer, ret in zip(peers, peer_returns, strict=True):
            _write(peer, 100.0, 100.0 * (1 + ret))

        settings_repo.set("watchlist", ",".join([target, *peers]), updated_by="test")

    try:
        ctx = CognitiveCycleContext(market={"symbol": target})
        result = ContextAdapter().to_relative_strength(ctx)

        assert result.basket_size == 3
        assert abs(result.symbol_return_pct - 0.10) < 1e-6
        assert abs(result.basket_mean_return_pct - 0.0) < 1e-6
        assert abs(result.relative_strength_pct - 0.10) < 1e-6
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("watchlist", original_watchlist, updated_by="test")


def test_to_relative_strength_waits_when_fewer_than_three_peers_have_data():
    from contracts.market_data import DataSource, MarketSnapshot, Resolution
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.repositories.market_data_repository import MarketDataRepository
    from database.session_factory import SessionFactory

    target = f"RSTGT{uuid4().hex[:6]}USDT"
    peer = f"RSPEER{uuid4().hex[:6]}USDT"
    base = datetime.now(UTC).replace(microsecond=0)

    with SessionFactory.get_session() as session:
        settings_repo = AppSettingsRepository(session)
        original_watchlist = settings_repo.get("watchlist")
        repo = MarketDataRepository(session)

        for sym in (target, peer):
            repo.upsert_snapshot(MarketSnapshot(
                time=base, exchange=DataSource.BINANCE, symbol=sym, resolution=Resolution.M1,
                open=100.0, high=100.0, low=100.0, close=100.0, volume=1.0, source_version="test",
            ))
            repo.upsert_snapshot(MarketSnapshot(
                time=base + timedelta(minutes=1), exchange=DataSource.BINANCE, symbol=sym,
                resolution=Resolution.M1, open=105.0, high=105.0, low=105.0, close=105.0,
                volume=1.0, source_version="test",
            ))

        settings_repo.set("watchlist", f"{target},{peer}", updated_by="test")

    try:
        ctx = CognitiveCycleContext(market={"symbol": target})
        result = ContextAdapter().to_relative_strength(ctx)

        assert result.basket_size < 3
        assert result.relative_strength_pct == 0.0
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("watchlist", original_watchlist, updated_by="test")
