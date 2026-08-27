"""Feature IC × Rejim — Faz 364-devam, kullanıcı isteği (2026-08-26):
"bu ölçümlerin hep rejime göre aynı kovalarda yapılması lazım, hangi
rejimde hangi sinyal işe yarıyor belki öyle bir korelasyon bulacağız."

analytics/feature_ic.py::compute_feature_ic() zaten GERÇEK feature
katkısı ile GERÇEK ileri getiri arasındaki korelasyonu hesaplıyor —
yeni bir istatistik YAZILMADI. Bu modül SADECE kapanmış işlemleri
market_regime'e göre önce gruplayıp, AYNI saf fonksiyonu her rejim
kovasında ayrı ayrı çağırıyor. Kasıtlı olarak SADECE ölçüm/rapor —
compute_feature_ic'in kendi ilkesiyle AYNI: hiçbir ajanın skorlamasını
otomatik değiştirmiyor."""
from collections import defaultdict

from analytics.feature_ic import MIN_SAMPLE_SIZE, compute_feature_ic


def compute_feature_ic_by_regime(
    closed_trades: list[dict], min_sample_size: int = MIN_SAMPLE_SIZE
) -> dict[str, dict[str, dict]]:
    """closed_trades: DecisionPersistor.list_closed_trades()'in döndürdüğü
    ham satırlar (market_regime sütunu dahil). Döner: {regime: {feature_
    name: {ic, p_value, sample_size, agent_domain}}} — market_regime'i
    olmayan (None) kayıtlar dışlanır, her rejim kovası kendi min_sample_
    size eşiğini bağımsız uygular (compute_feature_ic'in fail-closed
    disiplini, rejim bazında da korunuyor)."""
    by_regime: dict[str, list[dict]] = defaultdict(list)
    for trade in closed_trades:
        regime = trade.get("market_regime")
        if regime is None:
            continue
        by_regime[regime].append(trade)

    return {
        regime: compute_feature_ic(trades, min_sample_size=min_sample_size)
        for regime, trades in by_regime.items()
    }
