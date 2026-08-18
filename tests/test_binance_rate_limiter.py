"""exchange_gateway/binance/adapter.py::_throttle_binance_request —
gerçek olay (2026-08-18, canlıda 3 kez tekrarladı): çok sayıda Celery
worker süreci + paralel fetch'ler tek bir IP'den Binance'e çok yüksek
istek hızıyla gidip GERÇEKTEN IP banına (418) yol açtı. Bu, tüm
süreçlerin PAYLAŞTIĞI Redis sayacının gerçekten istek hızını sınırladığını
ve Redis erişilemezse fail-open davrandığını doğruluyor.

Testler kendi İZOLE anahtar önekini kullanır (canlı sistemin GERÇEK
binance_rate_limit anahtarını DEĞİL) — aksi halde arka planda çalışan
gerçek celery worker'ların (bu test oturumu boyunca canlı, aynı Redis'e
karşı gerçek Binance trafiği üreten) payına denk gelip testi kırılgan
kılardı; bu, o paylaşılan-durum davranışının kendisini test etmiyor,
sadece throttle mantığının doğruluğunu izole test ediyor."""
import time
from uuid import uuid4

import pytest

from exchange_gateway.binance.adapter import _MAX_REQUESTS_PER_SECOND, _throttle_binance_request


@pytest.fixture
def isolated_rate_limit_key(monkeypatch):
    import exchange_gateway.binance.adapter as adapter_module

    prefix = f"test_binance_rate_limit_{uuid4().hex[:8]}"
    monkeypatch.setattr(adapter_module, "_RATE_LIMIT_KEY_PREFIX", prefix)
    yield prefix

    import redis

    from config import get_settings

    client = redis.from_url(get_settings().REDIS_URL)
    bucket = int(time.time())
    for offset in (-1, 0, 1):
        client.delete(f"{prefix}:{bucket + offset}")


@pytest.mark.asyncio
async def test_throttle_allows_requests_under_the_limit_without_delay(isolated_rate_limit_key):
    start = time.monotonic()
    for _ in range(_MAX_REQUESTS_PER_SECOND):
        await _throttle_binance_request()
    elapsed = time.monotonic() - start

    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_throttle_delays_requests_once_the_per_second_cap_is_exceeded(isolated_rate_limit_key):
    for _ in range(_MAX_REQUESTS_PER_SECOND):
        await _throttle_binance_request()

    start = time.monotonic()
    await _throttle_binance_request()
    elapsed = time.monotonic() - start

    # Limit doldurulduktan sonraki istek en az bir backoff bekleyişi
    # kadar gecikmeli — sınırsız/anlık geçmemeli.
    assert elapsed >= 0.04


@pytest.mark.asyncio
async def test_throttle_fails_open_when_redis_is_unreachable(monkeypatch):
    import redis

    def _boom(*args, **kwargs):
        raise redis.exceptions.ConnectionError("redis unreachable")

    monkeypatch.setattr(redis, "from_url", _boom)

    # Redis'e hiç ulaşamasa bile exception fırlatmamalı — gerçek veri
    # çekme işlemini asla engellememeli (EventLogRepository.record ile
    # AYNI fail-open felsefesi).
    await _throttle_binance_request()
