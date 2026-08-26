"""Meta-Learning Effectiveness'ın girdisini GERÇEK onaylı ajan ayarlama
turlarından toplayan tek kaynak — Cognitive Core 2.0 (Faz 744-768).
analytics/meta_learning_effectiveness.py::compute_meta_learning_trend()
saf (pure) kalıyor — gerçek veriye dokunan kod burada."""
import json

from analytics.meta_learning_effectiveness import compute_meta_learning_trend


def gather_meta_learning_effectiveness() -> dict:
    from sqlalchemy import text

    from database.repositories.app_settings_repository import AppSettingsRepository
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

    sharpe_improvements = [r[0] for r in rows if r[0] is not None]
    last_attempt = json.loads(raw_last_attempt) if raw_last_attempt else None
    return {
        "trend": compute_meta_learning_trend(sharpe_improvements),
        "n_approved_rounds": len(sharpe_improvements),
        "last_attempt": last_attempt,
    }
