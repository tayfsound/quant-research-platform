"""Faz 268-sonrası — kullanıcı bulgusu: agents/relative_strength_agent.py
sadece ~49 sembollük watchlist içinde kıyaslama yapıyordu (services/
context_adapter.py::to_relative_strength, market_snapshots tablosundan —
kripto piyasası zaten yüksek korelasyonlu olduğu için bu neredeyse hiçbir
zaman anlamlı bir ayrışma bulamıyordu ("Watchlist ortalamasından belirgin
bir ayrışma yok" hep aynı sonuç). Kullanıcının kendi sözüyle: "Piyasadaki
bütün coinleri görüp ona göre kıyaslama yapması lazım."

Bu modül, Binance Futures'ın toplu 24hr ticker uç noktasını (TEK istekte
YÜZLERCE sembolün gerçek 24 saatlik fiyat değişimi) kullanır — services/
pump_fade_strategy.py'nin exchangeInfo taramasıyla AYNI disiplin: ağır,
sembol-başına istek yerine tek bulk çağrı. 5 dakika önbelleklenir — aynı
cycle içinde watchlist'teki her sembol için bu ajan ayrı ayrı çağrılınca
(run_portfolio_aware_cycle, tek cycle'da ~49 sembol) aynı veri onlarca
kez tekrar istenmesin."""
import time

import httpx
import structlog

logger = structlog.get_logger()

_TICKER_24HR_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"
_CACHE_TTL_SECONDS = 300
_cache: dict = {"data": None, "computed_at": 0.0}


def fetch_market_wide_24h_returns(force_refresh: bool = False) -> dict[str, float]:
    """{symbol: 24h fiyat değişim oranı (0.05 = %5)} — TÜM USDT-marjinli
    Binance Futures sözleşmeleri için. Ağ/HTTP hatasında fail-closed:
    önbellekte eski (ama gerçek) bir veri varsa onu döner, hiçbir veri
    yoksa boş dict — hiçbir zaman uydurma bir sayı üretilmez (çağıran
    taraf, agents/relative_strength_agent.py, boş/yetersiz veriyi zaten
    dürüstçe WAIT'e çeviriyor)."""
    now = time.time()
    if not force_refresh and _cache["data"] is not None and (now - _cache["computed_at"]) < _CACHE_TTL_SECONDS:
        return _cache["data"]

    try:
        resp = httpx.get(_TICKER_24HR_URL, timeout=15.0)
        resp.raise_for_status()
        rows = resp.json()
        result = {
            row["symbol"]: float(row["priceChangePercent"]) / 100.0
            for row in rows
            if row.get("symbol", "").endswith("USDT")
        }
    except Exception as exc:
        logger.warning("market_breadth_fetch_failed", error=str(exc))
        result = _cache["data"] or {}

    _cache["data"] = result
    _cache["computed_at"] = now
    return result
