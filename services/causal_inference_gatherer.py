"""Causal Inference'in girdisini GERÇEK piyasa verisinden toplayan tek
kaynak — Cognitive Core 4.0. analytics/causal_inference.py::compute_
granger_causality() saf (pure) kalıyor, gerçek veriye dokunan kod burada
— hem canlı API rotası (api/rest/causal_inference.py) hem haftalık
Celery task (services/tasks.py::refresh_causal_inference_report_task)
AYNI bu fonksiyonu çağırıyor.

Kapsam kasıtlı olarak sınırlı: TÜM sembol çiftlerini (207 sembol,
~43000 çift) test etmek hem hesaplama açısından mantıksız hem de çoğu
sembol için anlamsız (illikit/yeni listelenmiş) olurdu. Bunun yerine bu
sistemin gerçek multi-symbol backtest'lerinde zaten kullanılan 48
sembollük çekirdek listeden, en likit iki "piyasa lideri" (BTCUSDT,
ETHUSDT) SEBEP adayı olarak, listenin GERİ KALANI ETKİ adayı olarak
test ediliyor — "BTC/ETH'nin hareketi diğer varlıkları öngörüyor mu"
sorusuna gerçek veriyle cevap."""
from market_data.ingestion.data_provider import RoutingProvider

from analytics.causal_inference import compute_granger_causality

CAUSE_SYMBOLS = ["BTCUSDT", "ETHUSDT"]

# services/orchestrator.py'nin gerçek multi-symbol backtest'lerinde
# kullandığı AYNI çekirdek liste (Faz 268-sonrası) — tek bir yerde
# rastgele seçilmiş değil, bu oturumda zaten kanıtlanmış bir küme.
EFFECT_SYMBOLS = [
    "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "XAUTUSDT", "DOGEUSDT",
    "TRXUSDT", "LINKUSDT", "UNIUSDT", "NEARUSDT", "ZECUSDT", "AVAXUSDT",
    "DOTUSDT", "LTCUSDT", "ATOMUSDT", "APTUSDT", "ARBUSDT", "OPUSDT",
    "SUIUSDT", "INJUSDT", "FILUSDT", "ETCUSDT", "ICPUSDT", "BCHUSDT",
    "WLDUSDT", "TIAUSDT", "SEIUSDT", "RENDERUSDT", "AAVEUSDT", "ONDOUSDT",
    "LDOUSDT", "CRVUSDT", "GALAUSDT", "SANDUSDT", "AXSUSDT", "CHZUSDT",
    "CAKEUSDT", "ALGOUSDT", "XLMUSDT", "VETUSDT", "JUPUSDT",
    "AAPL", "NVDA", "MSFT", "GC=F", "SI=F", "^IXIC", "^GSPC",
]
BARS = 200
MAX_LAG = 5


def _fetch_returns(provider: RoutingProvider, symbol: str) -> list[float] | None:
    try:
        bars = provider.get_ohlcv(symbol, "1h", limit=BARS)
    except Exception:
        return None
    if len(bars) < 2:
        return None
    closes = [b.close for b in bars]
    return [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes)) if closes[i - 1]
    ]


def gather_causal_relationships() -> dict:
    provider = RoutingProvider()

    cause_returns = {s: r for s in CAUSE_SYMBOLS if (r := _fetch_returns(provider, s)) is not None}
    effect_returns = {s: r for s in EFFECT_SYMBOLS if (r := _fetch_returns(provider, s)) is not None}

    relationships = []
    pairs_tested = 0
    for cause_symbol, cause_series in cause_returns.items():
        for effect_symbol, effect_series in effect_returns.items():
            if cause_symbol == effect_symbol:
                continue
            n = min(len(cause_series), len(effect_series))
            if n < 30:
                continue
            pairs_tested += 1
            result = compute_granger_causality(
                cause_series[-n:], effect_series[-n:], max_lag=MAX_LAG
            )
            if result is not None and result["granger_causes"]:
                relationships.append({
                    "cause": cause_symbol,
                    "effect": effect_symbol,
                    "best_lag": result["best_lag"],
                    "best_p_value": result["best_p_value"],
                    "sample_size": result["sample_size"],
                })

    relationships.sort(key=lambda r: r["best_p_value"])
    return {
        "cause_symbols_tested": list(cause_returns.keys()),
        "effect_symbols_tested": list(effect_returns.keys()),
        "pairs_tested": pairs_tested,
        "significant_relationships": relationships,
    }
