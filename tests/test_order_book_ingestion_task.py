"""Faz 201: kritik bulgu — IngestionPipeline.ingest_order_book() tam
çalışan bir metod olarak yazılmıştı ama hiçbir üretim kodu hiç
çağırmıyordu. ingest_order_book_task bunu celery beat'e gerçekten
bağlıyor — OrderFlowAgent'ın veri açlığı çekmesinin kök nedeni."""
from unittest.mock import patch

from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from contracts.market_data import DataSource


def test_ingest_order_book_task_writes_real_snapshots_for_crypto_watchlist_symbols():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from services.celery_app import celery_app
        from services.tasks import ingest_order_book_task

        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                "watchlist", "BTCUSDT,ETHUSDT,AAPL", updated_by="test"
            )

        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True
        try:
            async_result = ingest_order_book_task.delay()
            assert async_result.successful()
            body = async_result.result
            # Sadece Binance sembolleri işlenmeli — AAPL (yfinance'te order
            # book derinliği yok) atlanmalı.
            assert set(body["ingested"].keys()) == {"BTCUSDT", "ETHUSDT"}
            for sym, result in body["ingested"].items():
                assert "error" not in result
                assert result["best_bid"] > 0
        finally:
            celery_app.conf.task_always_eager = False
            with SessionFactory.get_session() as session:
                from database.repositories.app_settings_repository import DEFAULTS
                AppSettingsRepository(session).set(
                    "watchlist", DEFAULTS["watchlist"], updated_by="test",
                )

    with SessionFactory.get_session() as session:
        row = MarketDataRepository(session).get_latest_order_book_snapshot(DataSource.BINANCE, "BTCUSDT")
    assert row is not None
    assert row["best_bid"] > 0
