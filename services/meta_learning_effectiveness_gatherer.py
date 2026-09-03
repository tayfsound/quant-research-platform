"""Meta-Learning Effectiveness'ın girdisini GERÇEK onaylı ajan ayarlama
turlarından toplayan tek kaynak — Cognitive Core 2.0 (Faz 744-768).
analytics/meta_learning_effectiveness.py::compute_meta_learning_trend()
saf (pure) kalıyor — gerçek veriye dokunan kod burada."""
import json

from analytics.measurement_stability import compute_stability
from analytics.meta_learning_effectiveness import compute_meta_learning_trend

STABILITY_LOOKBACK_SNAPSHOTS = 12
_TREND_STABILITY_FIELDS = ("spearman_correlation", "avg_sharpe_improvement")


def _attach_trend_stability(trend: dict | None, past_snapshots: list[dict]) -> None:
    """Faz 407 — kullanıcı isteği: "ölçtüğümüz her veri için zaman
    içindeki stabilitesini de ölçelim." Trend'in KENDİSİ (spearman_
    correlation) haftadan haftaya ne kadar tutarlı — yeni bir tur
    eklendikçe "improving"/"degrading" etiketi sık sık ters mi dönüyor
    yoksa istikrarlı mı? SADECE gözlem, trend etiketine hiç dokunmuyor."""
    if trend is None:
        return
    past_by_field: dict[str, list[float]] = {}
    for snap in past_snapshots:
        snap_trend = (snap.get("result") or {}).get("trend") or {}
        for field in _TREND_STABILITY_FIELDS:
            if snap_trend.get(field) is not None:
                past_by_field.setdefault(field, []).append(snap_trend[field])

    trend["stability"] = {
        field: compute_stability([*past_by_field.get(field, []), trend.get(field)])
        for field in _TREND_STABILITY_FIELDS
    }


def gather_meta_learning_effectiveness() -> dict:
    from sqlalchemy import text

    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.repositories.meta_learning_effectiveness_report_repository import (
        MetaLearningEffectivenessReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                "SELECT sharpe_improvement FROM agent_tuning_approvals "
                "WHERE status = 'approved' ORDER BY timestamp ASC"
            )
        ).all()
        # Faz 363 — kullanıcı bulgusu: onaylı tur hiç yokken panel sessizce
        # boş görünüyordu, "neden veri yok" sorusu tekrar tekrar soruldu.
        # services/meta_learning_scheduler.py artık HER denemenin (başarılı
        # ya da fail-closed skip) son sonucunu buraya yazıyor — panel en
        # azından "en son ne oldu, ne kadar eşiğin altında kaldı" diyebilsin.
        raw_last_attempt = AppSettingsRepository(session).get("meta_learning_last_attempt")
        past_snapshots = MetaLearningEffectivenessReportRepository(session).get_recent(
            STABILITY_LOOKBACK_SNAPSHOTS
        )

    sharpe_improvements = [r[0] for r in rows if r[0] is not None]
    last_attempt = json.loads(raw_last_attempt) if raw_last_attempt else None
    trend = compute_meta_learning_trend(sharpe_improvements)
    _attach_trend_stability(trend, past_snapshots)
    return {
        "trend": trend,
        "n_approved_rounds": len(sharpe_improvements),
        "last_attempt": last_attempt,
    }
