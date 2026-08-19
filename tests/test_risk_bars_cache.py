"""services/orchestrator.py::_get_risk_bars_cached — Faz 269-sonrası
kullanıcı isteği: gerçek olay, canlıda doğrulandı. Modül-seviyeli bir
dict önbelleği, celery worker'ın gerçekte 10 ayrı prefork SÜRECİ olarak
çalıştığı (varsayılan concurrency, `-c 1` DEĞİL) production'da 10 ayrı,
paylaşılmayan kopya demekti — önbellek isabet oranı vaat edilenin çok
altında kalıyordu. Artık Redis-tabanlı, TÜM süreçler arasında GERÇEKTEN
paylaşılan bir önbellek (services/tasks.py::_CycleLock ile AYNI desen)."""
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import redis

from config import get_settings
from market_data.ingestion.ohlcv import OHLCV
from services.orchestrator import (
    _RISK_BARS_CACHE_KEY_PREFIX,
    _RISK_BARS_CACHE_TTL_SECONDS,
    _get_risk_bars_cached,
)


class _CountingProvider:
    def __init__(self, bars: list):
        self.bars = bars
        self.call_count = 0

    def get_ohlcv(self, symbol, timeframe, limit=100):
        self.call_count += 1
        return self.bars


def _bars(n=3):
    now = datetime.now(UTC)
    return [
        OHLCV(timestamp=now - timedelta(days=n - i), open=100.0 + i, high=101.0, low=99.0, close=100.0, volume=1000.0)
        for i in range(n)
    ]


def _clear_cache_key(symbol: str, timeframe: str) -> None:
    client = redis.from_url(get_settings().REDIS_URL)
    client.delete(f"{_RISK_BARS_CACHE_KEY_PREFIX}:{symbol}:{timeframe}")


def test_get_risk_bars_cached_fetches_fresh_data_on_a_real_cache_miss():
    symbol = f"RBCTEST{uuid4().hex[:8]}"
    _clear_cache_key(symbol, "1d")
    provider = _CountingProvider(_bars())

    result = _get_risk_bars_cached(provider, symbol, timeframe="1d", limit=30)

    assert len(result) == 3
    assert provider.call_count == 1
    _clear_cache_key(symbol, "1d")


def test_get_risk_bars_cached_serves_the_second_call_from_redis_without_hitting_the_provider():
    """Bu, gerçek kullanıcı bulgusunun kanıtı: aynı sembol/timeframe için
    ikinci çağrı, provider'ı TEKRAR ÇAĞIRMADAN Redis'ten dönmeli — 10
    ayrı worker sürecinin HİÇBİRİ kendi izole kopyasını tutmuyor artık,
    hepsi AYNI Redis anahtarını paylaşıyor."""
    symbol = f"RBCTEST{uuid4().hex[:8]}"
    _clear_cache_key(symbol, "1d")
    provider = _CountingProvider(_bars())

    first = _get_risk_bars_cached(provider, symbol, timeframe="1d", limit=30)
    second = _get_risk_bars_cached(provider, symbol, timeframe="1d", limit=30)

    assert provider.call_count == 1  # ikinci çağrı önbellekten geldi
    assert [b.close for b in first] == [b.close for b in second]
    _clear_cache_key(symbol, "1d")


def test_get_risk_bars_cached_round_trips_real_ohlcv_fields_correctly():
    """Serileştirme/geri-okuma gerçek OHLCV alanlarını (timestamp dahil)
    kaybetmeden koruyor mu — bir tür/format hatası sessizce veri
    bozulmasına yol açmamalı."""
    symbol = f"RBCTEST{uuid4().hex[:8]}"
    _clear_cache_key(symbol, "1d")
    original = _bars()
    provider = _CountingProvider(original)

    _get_risk_bars_cached(provider, symbol, timeframe="1d", limit=30)
    cached = _get_risk_bars_cached(provider, symbol, timeframe="1d", limit=30)

    assert len(cached) == len(original)
    for o, c in zip(original, cached):
        assert c.open == o.open
        assert c.high == o.high
        assert c.low == o.low
        assert c.close == o.close
        assert c.volume == o.volume
        assert abs((c.timestamp - o.timestamp).total_seconds()) < 1e-6
    _clear_cache_key(symbol, "1d")


def test_get_risk_bars_cached_different_timeframes_are_independent():
    symbol = f"RBCTEST{uuid4().hex[:8]}"
    _clear_cache_key(symbol, "1d")
    _clear_cache_key(symbol, "4h")
    provider_daily = _CountingProvider(_bars(n=3))
    provider_4h = _CountingProvider(_bars(n=5))

    daily = _get_risk_bars_cached(provider_daily, symbol, timeframe="1d", limit=30)
    four_hour = _get_risk_bars_cached(provider_4h, symbol, timeframe="4h", limit=30)

    assert len(daily) == 3
    assert len(four_hour) == 5
    _clear_cache_key(symbol, "1d")
    _clear_cache_key(symbol, "4h")


def test_get_risk_bars_cached_expires_after_ttl(monkeypatch):
    """Redis'in kendi TTL'i (SETEX) gerçekten süresi dolunca yeni bir
    provider çağrısına düşmeli — sonsuza kadar bayat kalmamalı."""
    import services.orchestrator as orch_module

    monkeypatch.setattr(orch_module, "_RISK_BARS_CACHE_TTL_SECONDS", 1)
    symbol = f"RBCTEST{uuid4().hex[:8]}"
    _clear_cache_key(symbol, "1d")
    provider = _CountingProvider(_bars())

    _get_risk_bars_cached(provider, symbol, timeframe="1d", limit=30)
    assert provider.call_count == 1

    time.sleep(1.5)

    _get_risk_bars_cached(provider, symbol, timeframe="1d", limit=30)
    assert provider.call_count == 2  # TTL doldu, gerçekten yeniden çekildi
    _clear_cache_key(symbol, "1d")


def test_get_risk_bars_cached_fails_open_when_redis_is_unreachable(monkeypatch):
    """Redis'e hiç ulaşılamasa bile gerçek veri çekme işlemi asla
    engellenmemeli — Binance rate limiter/EventLogRepository ile AYNI
    fail-open felsefesi."""
    def _boom(*args, **kwargs):
        raise redis.exceptions.ConnectionError("redis unreachable")

    monkeypatch.setattr(redis, "from_url", _boom)
    symbol = f"RBCTEST{uuid4().hex[:8]}"
    provider = _CountingProvider(_bars())

    result = _get_risk_bars_cached(provider, symbol, timeframe="1d", limit=30)

    assert len(result) == 3
    assert provider.call_count == 1
