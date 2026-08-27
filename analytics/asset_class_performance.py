"""Varlık Sınıfı Performansı — kullanıcı isteği (2026-08-27): "Bitcoin/
Emtia/Hisse performansını dashboard bilgilendirme kartı olarak görmek
istiyorum... hangi işlem türünde AI ne kadar başarılı."

services/agent_memory.py::asset_class_of_symbol() ZATEN 4 alt-sınıf
ayırt ediyordu (gold_backed/precious_metal_future/equity_index/equity/
crypto) — Faz 325'in market-cap kalibrasyon çalışmasında kullanılmıştı.
Bu modül YENİ bir sınıflandırma icat etmiyor, aynı fonksiyonu kullanıp
kullanıcının istediği 3 kaba kategoriye (Kripto/Emtia/Hisse Senedi)
gruplayıp win_rate + Wilson güven aralığı hesaplıyor. Kasıtlı olarak
SADECE ölçüm/bilgilendirme."""
from collections import defaultdict

from analytics.collective_intelligence import compute_accuracy_confidence_interval
from services.agent_memory import asset_class_trading_category

MIN_SAMPLE_SIZE = 5

# services/agent_memory.py::asset_class_trading_category() TEK kaynak
# (crypto/commodity/equity) — burada sadece kullanıcının istediği
# Türkçe görünen etikete çevriliyor. "other" (hiçbiriyle eşleşmeyen
# semboller) kasıtlı olarak dışlanıyor.
CATEGORY_LABELS = {"crypto": "Kripto", "commodity": "Emtia", "equity": "Hisse Senedi"}


def compute_asset_class_performance(
    closed_trades: list[dict], min_sample_size: int = MIN_SAMPLE_SIZE,
) -> dict[str, dict]:
    """closed_trades: her biri {'symbol', 'pnl'} olan GERÇEK kapanmış
    işlemler. Döner: {kategori: {'win_rate', 'win_rate_ci', 'sample_size',
    'total_pnl'}} — min_sample_size altında kalan kategoriler fail-closed
    dışlanır. Kullanıcı isteği (2026-08-27): "bunların PNL'lerini de
    koyalım hangisi başarılı bileyim, zararda mı kârda mı" — win_rate
    yüksek ama toplam $ zararda olmak mümkün (ör. az sayıda büyük kayıp),
    bu yüzden ikisi BİRLİKTE gösteriliyor."""
    by_category: dict[str, list[float]] = defaultdict(list)
    for t in closed_trades:
        symbol = t.get("symbol")
        pnl = t.get("pnl")
        if not symbol or pnl is None:
            continue
        category = CATEGORY_LABELS.get(asset_class_trading_category(symbol))
        if category is None:
            continue
        by_category[category].append(pnl)

    result: dict[str, dict] = {}
    for category, pnls in by_category.items():
        n = len(pnls)
        if n < min_sample_size:
            continue
        win_count = sum(1 for p in pnls if p > 0)
        result[category] = {
            "win_rate": round(win_count / n, 4),
            "win_rate_ci": compute_accuracy_confidence_interval(win_count, n),
            "sample_size": n,
            "total_pnl": round(sum(pnls), 2),
        }
    return result
