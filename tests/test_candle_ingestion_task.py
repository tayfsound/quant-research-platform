"""Faz 207: kritik bulgu — IngestionPipeline.ingest_candles() (Market
Overview dashboard sayfasının /market-data/ohlcv endpoint'inin okuduğu tek
kaynak, market_snapshots tablosu) tam çalışan bir metod olarak yazılmıştı
ama hiçbir üretim kodu hiç çağırmıyordu — BTCUSDT dışında hiçbir sembol
için grafik verisi hiç yoktu. ingest_candles_task bunu celery beat'e
gerçekten bağlıyor."""
from unittest.mock import patch

from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from contracts.market_data import DataSource, Resolution


def test_ingest_candles_task_writes_real_snapshots_for_crypto_watchlist_symbols():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from services.celery_app import celery_app
        from services.tasks import ingest_candles_task

        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                "watchlist", "BTCUSDT,ETHUSDT,AAPL", updated_by="test"
            )

        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True
        try:
            async_result = ingest_candles_task.delay()
            assert async_result.successful()
            body = async_result.result
            # Sadece Binance sembolleri işlenmeli — AAPL (yfinance) atlanmalı.
            assert set(body["ingested"].keys()) == {"BTCUSDT", "ETHUSDT"}
            for sym, result in body["ingested"].items():
                assert isinstance(result, int), f"{sym} failed: {result}"
                assert result > 0
        finally:
            celery_app.conf.task_always_eager = False
            with SessionFactory.get_session() as session:
                from database.repositories.app_settings_repository import DEFAULTS
                AppSettingsRepository(session).set(
                    "watchlist", DEFAULTS["watchlist"], updated_by="test",
                )

    with SessionFactory.get_session() as session:
        rows = MarketDataRepository(session).get_latest_snapshots(
            DataSource.BINANCE, "ETHUSDT", Resolution("1m"), limit=1
        )
    assert len(rows) == 1
    assert rows[0].close > 0
