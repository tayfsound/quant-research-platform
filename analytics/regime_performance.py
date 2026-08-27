"""Rejim Performansı — kullanıcı isteği (2026-08-27): "REJİME GÖRE AI
KONSEYİ GİRİŞLERİ kartındaki butonlara hangi rejimin ne kadar başarılı
olduğu bilgisini ekleyelim, ROI gibi %63 atıyorum."

market_regime = "{trend}_{volatility_regime}" — pyramid_regime_gate.py/
strategy_regime_gate.py/regime_trading_gate.py ile AYNI format, aynı
AI-konseyi-özel popülasyon (pump_fade/basis_arb hariç zaten `market_
regime IS NOT NULL` + experiment_bucket ayrımı list_closed_trades'te
uygulanıyor). Kasıtlı olarak SADECE ölçüm/bilgilendirme."""
from collections import defaultdict

from analytics.collective_intelligence import compute_accuracy_confidence_interval

MIN_SAMPLE_SIZE = 5


def compute_regime_performance(
    closed_trades: list[dict], min_sample_size: int = MIN_SAMPLE_SIZE,
) -> dict[str, dict]:
    """closed_trades: her biri {'market_regime', 'pnl'} olan GERÇEK
    kapanmış AI konseyi kararları. Döner: {regime: {'win_rate',
    'win_rate_ci', 'sample_size', 'total_pnl'}}."""
    by_regime: dict[str, list[float]] = defaultdict(list)
    for t in closed_trades:
        regime = t.get("market_regime")
        pnl = t.get("pnl")
        if not regime or pnl is None:
            continue
        by_regime[regime].append(pnl)

    result: dict[str, dict] = {}
    for regime, pnls in by_regime.items():
        n = len(pnls)
        if n < min_sample_size:
            continue
        win_count = sum(1 for p in pnls if p > 0)
        result[regime] = {
            "win_rate": round(win_count / n, 4),
            "win_rate_ci": compute_accuracy_confidence_interval(win_count, n),
            "sample_size": n,
            "total_pnl": round(sum(pnls), 2),
        }
    return result
