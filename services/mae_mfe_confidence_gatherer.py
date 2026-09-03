"""MAE/MFE Bootstrap Güven Aralığı'nın girdisini GERÇEK kapanmış
işlemlerden toplayan tek kaynak — Cognitive Core 2.0 (Faz 469-493).
analytics/mae_mfe_scientific.py::bootstrap_quantile_ci() saf (pure)
kalıyor — gerçek veriye dokunan kod burada.

analytics/barrier_table_builder.py'nin GERÇEK trade çekme mantığıyla
(aynı SQL, aynı koşul kovaları: direction/regime/volatility_regime) AYNI
kaynak kullanılıyor — veri çekme icat/tekrar edilmiyor. Her kovanın |MAE|
noktası tahmini (compute_conditional_mae_distribution) ve bootstrap güven
aralığı (aynı kovadaki ham değerlerden) YAN YANA raporlanır.

Faz 367-devam — kullanıcı isteği (2026-08-28, yeni mae_mfe_bucket_
trading_gate'in AI-konseyi davranışını yansıtması gerektiği bulgusuyla):
paylaşılan _extract_real_trades_for_barrier_table() (Adaptive Barrier
Engine'in de kullandığı, PAYLAŞILAN kod yolu — kasıtlı olarak
DOKUNULMADI) pump_fade_v1/basis_arb_v1'i hariç TUTMUYORDU —
regime_performance_gatherer.py gibi kardeş "gerçek AI performansı"
modüllerinin zaten yaptığı AYNI izolasyon burada unutulmuştu. Filtre
SADECE bu gatherer'ın kendi çıktısında, services/asset_class_
performance_gatherer.py::_is_production_ai_council yeniden kullanılarak
uygulanıyor (aynı yardımcı fonksiyon, kod tekrarı yok)."""
from analytics.barrier_table_builder import _extract_real_trades_for_barrier_table
from analytics.barrier_table_repository import GROUP_BY
from analytics.mae_mfe import compute_conditional_mae_distribution
from analytics.mae_mfe_scientific import bootstrap_quantile_ci
from analytics.measurement_stability import compute_stability
from services.asset_class_performance_gatherer import _is_production_ai_council

DEFAULT_WINDOW = 2000
# compute_conditional_mae_distribution'ın örnek verdiği p90 MAE ile aynı
# quantile — nokta tahmini ile güven aralığı doğrudan karşılaştırılabilsin.
CI_QUANTILE = 0.9
STABILITY_LOOKBACK_SNAPSHOTS = 12


def _attach_p90_stability(point_estimates: dict[str, dict], past_snapshots: list[dict]) -> None:
    """Faz 407 — kullanıcı isteği: "ölçtüğümüz her veri için zaman
    içindeki stabilitesini de ölçelim." p90 MAE'nin (CI_QUANTILE ile
    doğrudan karşılaştırılan nokta tahmini) haftadan haftaya ne kadar
    tutarlı olduğunu ekliyor — SADECE gözlem."""
    past_by_label: dict[str, list[float]] = {}
    for snap in past_snapshots:
        for label, stat in ((snap.get("result") or {}).get("point_estimates") or {}).items():
            past_by_label.setdefault(label, []).append((stat.get("mae_quantiles") or {}).get("p90"))

    for label, stat in point_estimates.items():
        current_p90 = (stat.get("mae_quantiles") or {}).get("p90")
        stat["p90_stability"] = compute_stability([*past_by_label.get(label, []), current_p90])


def gather_mae_mfe_confidence(window: int = DEFAULT_WINDOW) -> dict:
    from database.repositories.mae_mfe_confidence_report_repository import (
        MaeMfeConfidenceReportRepository,
    )
    from database.session_factory import SessionFactory

    trades = _extract_real_trades_for_barrier_table(window)
    trades = [t for t in trades if _is_production_ai_council(t.get("experiment_bucket"))]

    with SessionFactory.get_session() as session:
        past_snapshots = MaeMfeConfidenceReportRepository(session).get_recent(STABILITY_LOOKBACK_SNAPSHOTS)

    point_estimates = compute_conditional_mae_distribution(trades, group_by=GROUP_BY)
    _attach_p90_stability(point_estimates, past_snapshots)

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
