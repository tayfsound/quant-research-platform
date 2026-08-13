"""Entry Timing — Faz 594-618 (Cognitive Core 2.0 / M5).

analytics/mae_mfe.py::compute_mae_mfe zaten time_to_mae_seconds/
time_to_mfe_seconds'ı hesaplıyor ama bunların DAĞILIMI hiç analiz
edilmemişti. Bu modül, MAE'nin GERÇEKTEN giriş anına ne kadar yakın
gerçekleştiğini ölçüyor — "hemen giriş" gürültüsünün (immediate adverse
excursion) ne kadar ciddi bir sorun olduğunu nicelendiriyor. Eğer MAE'nin
büyük çoğunluğu girişten hemen sonra (ör. ilk birkaç dakika) oluşuyorsa,
bu "biraz onay bekleme" (bir sonraki bar'ın kapanışını görme gibi)
fikrinin GERÇEK bir edge katıp katmayacağının ilk ölçümü.

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir giriş zamanlama kararını
burada otomatik değiştirmiyor."""

MIN_SAMPLE_SIZE = 20


def compute_immediate_adverse_excursion_rate(
    trades: list[dict],
    immediate_window_seconds: float,
) -> dict | None:
    """trades: mae_pct, time_to_mae_seconds alanları olan GERÇEK kapanmış
    işlemler (analytics/mae_mfe.py::compute_mae_mfe'nin çıktısı). MAE'si
    immediate_window_seconds içinde gerçekleşen trade'lerin oranını döner
    — GERÇEK bir dağılım istatistiği, icat edilmiş bir kural değil.
    <MIN_SAMPLE_SIZE gözlemle fail-closed None döner."""
    eligible = [
        t for t in trades
        if t.get("mae_pct") is not None and t.get("time_to_mae_seconds") is not None
    ]
    if len(eligible) < MIN_SAMPLE_SIZE:
        return None

    immediate = [t for t in eligible if t["time_to_mae_seconds"] <= immediate_window_seconds]
    immediate_rate = len(immediate) / len(eligible)

    avg_mae_immediate = (
        sum(abs(t["mae_pct"]) for t in immediate) / len(immediate) if immediate else None
    )
    later = [t for t in eligible if t["time_to_mae_seconds"] > immediate_window_seconds]
    avg_mae_later = (
        sum(abs(t["mae_pct"]) for t in later) / len(later) if later else None
    )

    return {
        "sample_size": len(eligible),
        "immediate_window_seconds": immediate_window_seconds,
        "immediate_mae_count": len(immediate),
        "immediate_mae_rate": round(immediate_rate, 4),
        "avg_mae_pct_when_immediate": round(avg_mae_immediate, 6) if avg_mae_immediate is not None else None,
        "avg_mae_pct_when_later": round(avg_mae_later, 6) if avg_mae_later is not None else None,
    }
