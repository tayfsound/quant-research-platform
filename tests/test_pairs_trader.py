"""Faz 200: PairsTrader — kointegre bir çift gerçekten sapınca iki bacaklı
(bir LONG bir SHORT) gerçek pozisyon açıyor mu, mevcut risk altyapısını
(ai_enabled/cooldown/trading_mode) gerçekten kullanıyor mu."""
from unittest.mock import patch
from uuid import uuid4

import numpy as np

from database.repositories.app_settings_repository import DEFAULTS, AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from market_data.ingestion.ohlcv import OHLCV
from services.pairs_trader import PairsTrader


def _cointegrated_bars(n=100, seed=1, diverge_last=0.0):
    rng = np.random.RandomState(seed)
    common = np.cumsum(rng.normal(0, 1, n)) + 100
    noise = rng.normal(0, 0.5, n)
    a = common.copy()
    b = common + noise
    a[-1] += diverge_last

    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC)
    bars_a = [OHLCV(timestamp=now - timedelta(minutes=n - i), open=v, high=v, low=v, close=v, volume=1.0) for i, v in enumerate(a)]
    bars_b = [OHLCV(timestamp=now - timedelta(minutes=n - i), open=v, high=v, low=v, close=v, volume=1.0) for i, v in enumerate(b)]
    return bars_a, bars_b


class _FakeProvider:
    def __init__(self, bars_by_symbol: dict):
        self.bars_by_symbol = bars_by_symbol

    def get_ohlcv(self, symbol, timeframe, limit=100):
        return self.bars_by_symbol.get(symbol, [])


def test_pair_with_extreme_divergence_opens_both_legs():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        sym_a, sym_b = f"PAIRA{uuid4().hex[:6]}USDT", f"PAIRB{uuid4().hex[:6]}USDT"
        bars_a, bars_b = _cointegrated_bars(diverge_last=3.0)
        provider = _FakeProvider({sym_a: bars_a, sym_b: bars_b})

        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("ai_enabled", "true", updated_by="test")
            AppSettingsRepository(session).set("trading_mode", "test", updated_by="test")
            # Faz 262: kritik bulgu — RiskEngine artık test modunda da
            # gerçek kasa/eşzamanlılık limitlerini uyguluyor (bkz.
            # engines/risk_engine.py). Bu test paylaşılan/kirlenmiş test
            # DB'sinin GERÇEK birikmiş kapasitesinden bağımsız,
            # kointegrasyon/zscore mantığını doğruluyor — kasa limitlerini
            # kasıtlı olarak bol tutuyoruz.
            # Gerçek bulgu: paylaşılan test DB'si, bu oturum boyunca hiç
            # temizlenmeden biriken "open" pozisyonlardan dolayı
            # capital_used_pct'i zaten >%600'e taşımış durumda (gerçek
            # kapanmamış test verisi, starting_capital'ın test varsayılanı
            # küçük olduğu için) — "1.0" (yani %100) bile yetersiz kalıyordu.
            # Bu test kasa muhasebesini değil kointegrasyon/yön mantığını
            # doğruluyor, o yüzden sınırı kasıtlı olarak çok bol tutuyoruz.
            AppSettingsRepository(session).set("max_capital_pct", "1000000", updated_by="test")
            AppSettingsRepository(session).set("max_concurrent_positions", "100000", updated_by="test")
            # Kill switch (2026-08-12) — AYNI paylaşılan-DB-kirlenmesi
            # gerekçesi: bu oturumda biriken gerçek kapanmış kayıp
            # işlemler, kointegrasyon mantığıyla ilgisi olmayan bu testte
            # devre kesiciyi tetikleyebilir. Devre dışı bırakılıyor.
            AppSettingsRepository(session).set("kill_switch_consecutive_losses", "0", updated_by="test")

        trader = PairsTrader(data_provider=provider)
        try:
            result = trader._check_pair(sym_a, sym_b)

            assert result["cointegrated"] is True
            assert abs(result["zscore"]) >= 2.0
            assert set(result["opened_legs"]) == {sym_a, sym_b}
        finally:
            with SessionFactory.get_session() as session:
                repo = AppSettingsRepository(session)
                repo.set("max_capital_pct", DEFAULTS["max_capital_pct"], updated_by="test")
                repo.set("max_concurrent_positions", DEFAULTS["max_concurrent_positions"], updated_by="test")

    with SessionFactory.get_session() as session:
        repo = DecisionPersistor(session)
        rows_a = [r for r in repo.list_open_positions(limit=200) if r["symbol"] == sym_a]
        rows_b = [r for r in repo.list_open_positions(limit=200) if r["symbol"] == sym_b]

    assert len(rows_a) == 1
    assert len(rows_b) == 1
    # Biri LONG biri SHORT olmalı — aynı yönde iki bacak pairs trade değildir.
    assert {rows_a[0]["direction"], rows_b[0]["direction"]} == {"LONG", "SHORT"}


def test_pair_without_divergence_opens_nothing():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        sym_a, sym_b = f"PAIRC{uuid4().hex[:6]}USDT", f"PAIRD{uuid4().hex[:6]}USDT"
        bars_a, bars_b = _cointegrated_bars(diverge_last=0.0)
        provider = _FakeProvider({sym_a: bars_a, sym_b: bars_b})

        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("ai_enabled", "true", updated_by="test")

        trader = PairsTrader(data_provider=provider)
        result = trader._check_pair(sym_a, sym_b)

        assert "opened_legs" not in result


def test_pairs_trader_skips_everything_when_ai_disabled():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("ai_enabled", "false", updated_by="test")

        trader = PairsTrader(data_provider=_FakeProvider({}))
        results = trader.check_and_trade_pairs()

        assert results == [{"skipped": "ai_disabled"}]

        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("ai_enabled", "true", updated_by="test")


def test_uncointegrated_pair_is_reported_as_such():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        sym_a, sym_b = f"INDA{uuid4().hex[:6]}USDT", f"INDB{uuid4().hex[:6]}USDT"
        rng = np.random.RandomState(7)
        n = 100
        a_vals = np.cumsum(rng.normal(0, 1, n)) + 100
        b_vals = np.cumsum(rng.normal(0, 1, n)) + 500

        from datetime import UTC, datetime, timedelta
        now = datetime.now(UTC)
        bars_a = [OHLCV(timestamp=now - timedelta(minutes=n - i), open=v, high=v, low=v, close=v, volume=1.0) for i, v in enumerate(a_vals)]
        bars_b = [OHLCV(timestamp=now - timedelta(minutes=n - i), open=v, high=v, low=v, close=v, volume=1.0) for i, v in enumerate(b_vals)]
        provider = _FakeProvider({sym_a: bars_a, sym_b: bars_b})

        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("ai_enabled", "true", updated_by="test")

        trader = PairsTrader(data_provider=provider)
        result = trader._check_pair(sym_a, sym_b)

        assert result["cointegrated"] is False
