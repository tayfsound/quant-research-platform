"""Faz 410 — kullanıcı isteği: sentiment_agent'ın google_trends_score alanı
hiçbir zaman gerçek bir veri kaynağına bağlanmamıştı — contracts/sentiment.py
sabit varsayılanda (50.0, tam nötr orta nokta) donuk kalıyordu, hiçbir
zaman >80/<20 eşiklerini geçemiyordu. pytrends (resmi olmayan ama yaygın
kullanılan, ücretsiz, API anahtarı gerektirmeyen bir Google Trends
istemcisi) üzerinden gerçek arama ilgisi (0-100, Google'ın KENDİ ölçeği —
sentiment_agent'ın beklediği aralıkla dönüşümsüz uyumlu) çekiyor.

fred_provider.py ile AYNI desen: süreç-içi önbellek + fail-closed None
(veri çekilemezse icat edilmiş bir sayı asla üretilmez, çağıran taraf
mevcut nötr varsayılana düşer)."""
import logging
import time

logger = logging.getLogger(__name__)

# pytrends resmi olmayan bir istemci — çok sık istek atmak Google
# tarafından rate-limit/geçici blok riski taşıyor. Arama ilgisi zaten
# saatler içinde çok değişmiyor, uzun bir TTL hem güvenli hem yeterli.
_CACHE_TTL_SECONDS = 4 * 3600
_CACHE: dict[str, tuple[float, float | None]] = {}

# Ticker'dan gerçek arama terimine — ham ticker de (ör. "SUI") çoğu zaman
# makul sonuç verir, ama bilinen büyük varlıklar için gerçek isim çok daha
# temiz bir sinyal üretiyor (ör. "BTC" hem Bitcoin hem başka aramalara
# karışabilir, "Bitcoin" karışmaz).
_SYMBOL_TO_QUERY = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "BNB": "BNB crypto",
    "XRP": "XRP crypto", "ADA": "Cardano", "DOGE": "Dogecoin", "TRX": "TRON crypto",
    "LINK": "Chainlink", "AVAX": "Avalanche crypto", "DOT": "Polkadot crypto",
    "LTC": "Litecoin", "ATOM": "Cosmos crypto", "ETC": "Ethereum Classic",
    "BCH": "Bitcoin Cash", "XLM": "Stellar crypto", "XMR": "Monero crypto",
    "SHIB": "Shiba Inu crypto", "PEPE": "Pepe coin", "BONK": "Bonk crypto",
    "FLOKI": "Floki crypto", "UNI": "Uniswap", "AAVE": "Aave crypto",
    "1000SHIB": "Shiba Inu crypto", "1000PEPE": "Pepe coin", "1000BONK": "Bonk crypto",
    "1000FLOKI": "Floki crypto",
    "XAUT": "gold price", "XAG": "silver price", "PAXG": "gold price",
    "NVDA": "Nvidia stock", "AAPL": "Apple stock", "MSFT": "Microsoft stock",
    "GOOGL": "Google stock", "AMZN": "Amazon stock", "META": "Meta stock",
    "TSLA": "Tesla stock", "NFLX": "Netflix stock", "AMD": "AMD stock",
    "INTC": "Intel stock", "COIN": "Coinbase stock", "MSTR": "MicroStrategy stock",
    "PLTR": "Palantir stock", "QQQ": "Nasdaq", "SPX": "SP500",
}


def _base_symbol(symbol: str) -> str:
    s = symbol.upper()
    for suffix in ("USDT", "BUSD", "USDC", "FDUSD"):
        if s.endswith(suffix):
            return s[: -len(suffix)]
    return s


def fetch_google_trends_score(symbol: str) -> float | None:
    """Son 7 günün en son saatlik arama-ilgi puanını (0-100) döner. Ağ
    hatası/pytrends engeli/tanınmayan sembol -> None (icat edilmiş bir
    nötr değer asla üretilmez — çağıran taraf mevcut fail-closed
    varsayılana düşer)."""
    base = _base_symbol(symbol)
    query = _SYMBOL_TO_QUERY.get(base, base)

    cached = _CACHE.get(query)
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=0)
        pytrends.build_payload([query], cat=0, timeframe="now 7-d", geo="", gprop="")
        df = pytrends.interest_over_time()
        result = float(df[query].iloc[-1]) if not df.empty else None
        _CACHE[query] = (time.monotonic(), result)
        return result
    except Exception as exc:
        logger.warning("Google Trends fetch failed (%s): %s", query, exc)
        _CACHE[query] = (time.monotonic(), None)
        return None
