"""MAE/MFE Bootstrap Güven Aralığı'nın girdisini GERÇEK kapanmış
işlemlerden toplayan tek kaynak — Cognitive Core 2.0 (Faz 469-493).
analytics/mae_mfe_scientific.py::bootstrap_quantile_ci() saf (pure)
kalıyor — gerçek veriye dokunan kod burada.

analytics/barrier_table_builder.py'nin GERÇEK trade çekme mantığıyla
(aynı SQL, aynı koşul kovaları: direction/regime/volatility_regime) AYNI
kaynak kullanılıyor — veri çekme icat/tekrar edilmiyor. Her kovanın |MAE|
noktası tahmini (compute_conditional_mae_distribution) ve bootstrap güven
aralığı (aynı kovadaki ham değerlerden) YAN YANA raporlanır."""
from analytics.barrier_table_builder import _extract_real_trades_for_barrier_table
from analytics.barrier_table_repository import GROUP_BY
from analytics.mae_mfe import compute_conditional_mae_distribution
from analytics.mae_mfe_scientific import bootstrap_quantile_ci

DEFAULT_WINDOW = 2000
# compute_conditional_mae_distribution'ın örnek verdiği p90 MAE ile aynı
# quantile — nokta tahmini ile güven aralığı doğrudan karşılaştırılabilsin.
CI_QUANTILE = 0.9


def gather_mae_mfe_confidence(window: int = DEFAULT_WINDOW) -> dict:
    trades = _extract_real_trades_for_barrier_table(window)

    point_estimates = compute_conditional_mae_distribution(trades, group_by=GROUP_BY)

    groups: dict[tuple, list[float]] = {}
    for t in trades:
        if t.get("mae_pct") is None:
            continue
        key = tuple(str(t.get(field, "unknown")) for field in GROUP_BY)
        groups.setdefault(key, []).append(abs(t["mae_pct"]))

    confidence_intervals: dict[str, dict] = {}
    for key, values in groups.items():
        label = "|".join(f"{field}={value}" for field, value in zip(GROUP_BY, key))
        ci = bootstrap_quantile_ci(values, quantile=CI_QUANTILE)
        if ci is not None:
            confidence_intervals[label] = ci

    return {
        "quantile": CI_QUANTILE,
        "point_estimates": point_estimates,
        "confidence_intervals": confidence_intervals,
        "total_trades": len(trades),
    }
