"""Kullanıcı isteği: onchain ajanının gerçek sinyali (network_activity_
trend/hash_rate_trend/mvrv_zscore) SADECE Bitcoin zincirinden geliyor —
BTC dışındaki sembollerde onchain'in söyleyecek gerçek hiçbir şeyi yok,
council'i hiç etkilememeli (bkz. services/orchestrator.py::
build_cognitive_context, contracts/contexts/market.py::
data_unavailable_domains)."""
from datetime import UTC, datetime

from market_data.ingestion.ohlcv import OHLCV
from services.orchestrator import build_cognitive_context


def _bars(n: int = 30) -> list[OHLCV]:
    return [
        OHLCV(timestamp=datetime.now(UTC), open=100.0, high=101.0, low=99.0, close=100.0, volume=10.0)
        for _ in range(n)
    ]


def test_non_btc_symbol_excludes_onchain_domain():
    ctx = build_cognitive_context("ETHUSDT", "1m", _bars())
    assert ctx.market.data_unavailable_domains == ["onchain"]


def test_btc_symbol_does_not_exclude_onchain_domain():
    ctx = build_cognitive_context("BTCUSDT", "1m", _bars())
    assert "onchain" not in ctx.market.data_unavailable_domains


def test_non_crypto_symbol_also_excludes_onchain_domain():
    ctx = build_cognitive_context("^GSPC", "1d", _bars())
    assert ctx.market.data_unavailable_domains == ["onchain"]
