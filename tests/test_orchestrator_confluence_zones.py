"""services/orchestrator.py::build_cognitive_context — Faz 299-300.
Kullanıcı isteği: TP/SL Confluence canlıya bağlandı. ctx.market.features
artık her cycle'da "confluence_zones" (analytics/tp_sl_confluence.py::
compute_price_levels + compute_confluence_zones) taşıyor — RiskTargetStage
bunu okuyup hedefi (SADECE hedefi) gerçek bir yapısal bölgeye yakınsa
sıkılaştırıyor."""
import math
from datetime import UTC, datetime, timedelta

from market_data.ingestion.ohlcv import OHLCV
from services.orchestrator import build_cognitive_context


def _oscillating_bars(n: int = 250, start: float = 100.0, amplitude: float = 8.0) -> list[OHLCV]:
    """Gerçek swing high/low'lar üretecek dalgalı bir seri — düz/sabit
    fiyatla S/R zone clustering hiçbir şey bulamaz (test_signal_engine.py
    ile AYNI desen)."""
    base = datetime.now(UTC)
    bars = []
    for i in range(n):
        close = start + amplitude * math.sin(i * 0.3) + i * 0.02
        bars.append(OHLCV(
            timestamp=base + timedelta(hours=i),
            open=close, high=close + 0.5, low=close - 0.5, close=close, volume=100.0,
        ))
    return bars


def test_build_cognitive_context_populates_confluence_zones_key():
    ctx = build_cognitive_context("BTCUSDT", "1h", _oscillating_bars())
    assert "confluence_zones" in ctx.market.features
    assert isinstance(ctx.market.features["confluence_zones"], list)


def test_build_cognitive_context_confluence_zones_have_real_shape_when_found():
    ctx = build_cognitive_context("BTCUSDT", "1h", _oscillating_bars())
    zones = ctx.market.features["confluence_zones"]
    for zone in zones:
        assert "level" in zone
        assert "method_count" in zone
        assert zone["method_count"] >= 1
        assert isinstance(zone["contributing_methods"], list)


def test_build_cognitive_context_fails_closed_with_flat_price_series():
    """Sabit fiyatlı (swing'siz) bir seride confluence_zones anahtarı
    yine var olmalı ama muhtemelen boş/az sayıda öğe içermeli — icat
    edilmiş bir seviye asla üretilmez."""
    base = datetime.now(UTC)
    bars = [
        OHLCV(timestamp=base + timedelta(hours=i), open=100.0, high=100.1, low=99.9, close=100.0, volume=10.0)
        for i in range(30)
    ]
    ctx = build_cognitive_context("BTCUSDT", "1h", bars)
    assert "confluence_zones" in ctx.market.features
    assert isinstance(ctx.market.features["confluence_zones"], list)
