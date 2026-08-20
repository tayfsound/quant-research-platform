"""Binance için paylaşılan hız sınırlama — Faz 269-sonrası'nda
exchange_gateway/binance/adapter.py içinde yazılmıştı, Faz 315'te
(Execution Layer) futures_execution_adapter.py'nin de AYNI Redis
sayacını paylaşabilmesi için buraya çıkarıldı.

Gerçek olay (2026-08-18, canlıda 3 kez tekrarladı): çok sayıda Celery
worker süreci + her birinin kendi paralel ThreadPoolExecutor fetch'leri,
TEK bir IP'den Binance'e kısa sürede çok yüksek istek hızıyla gitti ve
GERÇEKTEN IP banına (418 "I'm a teapot") yol açtı. services/tasks.py::
_CycleLock'un kullandığı AYNI Redis-tabanlı paylaşılan-durum deseni:
sabit-pencere sayaç (fixed-window counter) — standart, iyi bilinen bir
distributed rate-limiting tekniği, icat edilmiş bir formül değil. Tüm
süreçler (ve artık hem spot okuma hem futures emir gönderimi) AYNI Redis
sayacını paylaştığı için TOPLAM istek hızı sınırlanıyor.

Emir gönderimi (place_order/cancel_order) spot okumadan (klines/depth)
DAHA DÜŞÜK hacimli ama DAHA YÜKSEK riskli çağrılar — aynı fixed-window
sayaç yeterli, ayrı bir bütçe icat edilmedi (basitlik, tek gerçek
kaynak)."""
import asyncio
import random
import time

from config import get_settings

_RATE_LIMIT_KEY_PREFIX = "binance_rate_limit"
# Binance spot ağırlık limiti dakikada 6000 (~100/sn) — küçük-limitli
# klines/depth/trades istekleri genelde ağırlık 1-5 arası, bu yüzden
# saniyede 15 İSTEK konservatif bir pay bırakıyor (~%50-75 ağırlık
# marjı), kendi kendimizi banlamayı önlerken canlı döngüyü fazla
# yavaşlatmıyor.
_MAX_REQUESTS_PER_SECOND = 15
_MAX_THROTTLE_WAIT_SECONDS = 5.0


async def throttle_binance_request() -> None:
    """Redis erişilemezse (ör. kısa bir kesinti) FAIL-OPEN: hiç
    yavaşlatmadan devam eder — bir yardımcı altyapı bileşeninin kendisi,
    asıl veri çekme/emir gönderme işlemini asla engellememeli
    (EventLogRepository.record ile AYNI felsefe)."""
    try:
        import redis

        client = redis.from_url(get_settings().REDIS_URL)
        waited = 0.0
        while waited < _MAX_THROTTLE_WAIT_SECONDS:
            bucket = int(time.time())
            key = f"{_RATE_LIMIT_KEY_PREFIX}:{bucket}"
            count = client.incr(key)
            if count == 1:
                client.expire(key, 2)
            if count <= _MAX_REQUESTS_PER_SECOND:
                return
            sleep_for = 0.05 + random.random() * 0.05
            await asyncio.sleep(sleep_for)
            waited += sleep_for
    except Exception:
        return
