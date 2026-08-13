"""Seasonality Detection — gün-içi saat ve haftanın günü bazlı GERÇEK
performans farkları.

Neden gerekli: eğer AI'nin gerçek kazanma oranı/PnL'i belirli saatlerde
(ör. düşük likidite periyotları) ya da haftanın belirli günlerinde
sistematik olarak farklıysa, bu ZATEN var olan bir sinyal — icat edilmiş
bir "seasonality stratejisi" değil, gerçek geçmiş performansın zaman-bazlı
bir kırılımı. Kruskal-Wallis (nonparametric, pnl dağılımının normal
olduğunu VARSAYMAZ) ile kovalar arası fark rastgele mi gerçek mi diye
tek bir p-value'da özetleniyor — az sayıda kova gürültüsünden "seasonality
var" sonucu icat edilmiyor.

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir zamanlama kararını (ör. belirli
saatlerde işlem açmayı durdurma) burada otomatik UYGULAMIYOR."""
from collections import defaultdict
from datetime import datetime
from typing import Callable

MIN_BUCKET_SIZE = 20


def _compute_seasonality(
    trades: list[dict],
    key_fn: Callable[[datetime], int],
    min_bucket_size: int = MIN_BUCKET_SIZE,
) -> dict:
    buckets: dict[int, list[dict]] = defaultdict(list)
    for t in trades:
        opened_at = t.get("opened_at")
        pnl = t.get("pnl")
        if opened_at is None or pnl is None:
            continue
        buckets[key_fn(opened_at)].append(t)

    eligible = {k: v for k, v in buckets.items() if len(v) >= min_bucket_size}

    result: dict = {"buckets": {}, "significance": {"p_value": None, "significant": None}}
    for key, group in eligible.items():
        pnls = [g["pnl"] for g in group]
        wins = sum(1 for p in pnls if p > 0)
        result["buckets"][str(key)] = {
            "sample_size": len(group),
            "win_rate": round(wins / len(group), 4),
            "avg_pnl": round(sum(pnls) / len(pnls), 6),
            "total_pnl": round(sum(pnls), 6),
        }

    # Faz 268-sonrası: en az 2 uygun kova yoksa (fail-closed) anlamlılık
    # testi hiç YAPILMIYOR — tek kovadan "fark var/yok" icat edilmez.
    if len(eligible) >= 2:
        from scipy import stats

        groups_pnls = [[g["pnl"] for g in group] for group in eligible.values()]
        stat_result = stats.kruskal(*groups_pnls)
        result["significance"] = {
            "p_value": round(float(stat_result.pvalue), 6),
            "significant": bool(stat_result.pvalue < 0.05),
        }

    return result


def compute_hourly_seasonality(trades: list[dict], min_bucket_size: int = MIN_BUCKET_SIZE) -> dict:
    """trades: opened_at (UTC datetime) ve pnl alanı olan gerçek kapanmış
    işlemler (ör. DecisionPersistor.list_closed_trades()). UTC saatine
    (0-23) göre gruplar."""
    return _compute_seasonality(trades, key_fn=lambda dt: dt.hour, min_bucket_size=min_bucket_size)


def compute_day_of_week_seasonality(trades: list[dict], min_bucket_size: int = MIN_BUCKET_SIZE) -> dict:
    """0=Pazartesi..6=Pazar (Python datetime.weekday() konvansiyonu)."""
    return _compute_seasonality(trades, key_fn=lambda dt: dt.weekday(), min_bucket_size=min_bucket_size)
