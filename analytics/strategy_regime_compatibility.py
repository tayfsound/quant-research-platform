"""Strategy × Regime Compatibility — Faz 338 (MetaStrategyAgent v1).

Kullanıcı onayı, harici bir AI incelemesinin önerisi: "Bu stratejinin şu
anki piyasa rejiminde gerçek/OOS-koşullu edge'i var mı?" sorusuna GERÇEK
geçmiş verilerle cevap veren, ölçüm-only bir modül. pump_fade'in bugünkü
felaketiyle DOĞRUDAN ilgili: "piyasa güçlü yükseliş trendindeyken
pump_fade (SHORT-only mekanik strateji) hâlâ tam boyutta işlem açıyor"
sorununun GENEL, tüm stratejiler için tekrarlanabilir hali.

Kasıtlı olarak SADECE ölçüm/rapor — v1'de HİÇBİR gate'e otomatik
bağlanmıyor, hiçbir stratejiyi ALLOW/REDUCE/BLOCK etmiyor. "Yeni meta-
model = ölçüm-only, hemen güvenli; ama gerçek karara (otomatik
engelleme/yönlendirme) bağlamak = ayrı, açık bir onay + OOS kanıtı
gerektirir" ilkesi (kullanıcı + harici AI incelemesi ortak kararı)."""
from collections import defaultdict

from analytics.collective_intelligence import compute_accuracy_confidence_interval

MIN_GROUP_SIZE = 15


def compute_strategy_regime_compatibility(
    records: list[dict],
    min_group_size: int = MIN_GROUP_SIZE,
) -> dict:
    """records: her biri {'strategy', 'market_regime', 'win'} olan GERÇEK
    kapanmış işlemler. strategy × market_regime kombinasyonuna göre
    gruplayıp win_rate hesaplar — hem her stratejinin KENDİ genel
    (tüm-rejim) win_rate'iyle karşılaştırma (delta) hem de min_group_size
    altındaki kovaların fail-closed dışlanması dahil.

    Döner: {strategy: {"overall_win_rate": ..., "overall_sample_size": ...,
    "by_regime": {regime: {"sample_size", "win_rate", "win_rate_ci",
    "delta_vs_overall"}}}}"""
    by_strategy: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        strategy = r.get("strategy")
        regime = r.get("market_regime")
        win = r.get("win")
        if strategy is None or regime is None or win is None:
            continue
        by_strategy[strategy].append(r)

    result: dict = {}
    for strategy, strategy_records in by_strategy.items():
        overall_wins = sum(1 for r in strategy_records if r["win"])
        overall_n = len(strategy_records)
        overall_win_rate = round(overall_wins / overall_n, 4) if overall_n > 0 else None

        by_regime_records: dict[str, list[dict]] = defaultdict(list)
        for r in strategy_records:
            by_regime_records[r["market_regime"]].append(r)

        by_regime: dict = {}
        for regime, regime_records in by_regime_records.items():
            if len(regime_records) < min_group_size:
                continue
            wins = sum(1 for r in regime_records if r["win"])
            n = len(regime_records)
            win_rate = round(wins / n, 4)
            by_regime[regime] = {
                "sample_size": n,
                "win_rate": win_rate,
                "win_rate_ci": compute_accuracy_confidence_interval(wins, n),
                "delta_vs_overall": round(win_rate - overall_win_rate, 4) if overall_win_rate is not None else None,
            }

        result[strategy] = {
            "overall_win_rate": overall_win_rate,
            "overall_sample_size": overall_n,
            "by_regime": by_regime,
        }

    return result
