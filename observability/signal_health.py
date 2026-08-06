"""Faz 230: kullanıcı isteği — Faz 203-211'deki 7 katmanlı sessiz-hata
zincirinin ("AI hiç işlem açmıyor", hiçbir katman exception fırlatmıyordu)
bir daha sessizce yaşanmaması için gerçek bir izleme katmanı. observability/
health.py'nin K8s-tarzı /health'i sadece "süreç ayakta mı, DB'ye erişilebiliyor
mu" sorusuna cevap veriyor — bu modül farklı, çok daha değerli bir soruya
cevap veriyor: "her modül GERÇEKTEN güncel veri üretiyor mu, yoksa sessizce
mi donmuş?" Her eşik, celery_app.py'deki gerçek zamanlanma aralığının
(bkz. services/celery_app.py::beat_schedule) birkaç katı — geçici bir
gecikmeyi false-positive olarak işaretlememek için."""
from datetime import UTC, datetime

from sqlalchemy import text

from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory

# celery_app.py'deki gerçek zamanlamalar: candle 60s, order-book 20s,
# trading-cycle 120s. Eşikler bunların ~5 katı — ağ gecikmesi/tekil bir
# atlanan tick false alarm üretmesin, ama gerçek bir donma (dakikalarca
# değil saatlerce) yakalanır.
_STALE_THRESHOLDS_SECONDS = {
    "candle_ingestion": 300,
    "order_book_ingestion": 100,
    "trading_cycle": 600,
}

# Faz 203-211'in gerçek imzası: sistem "çalışıyor" (cycle'lar üretiliyor)
# ama HİÇBİR zaman gerçek yönlü (LONG/SHORT) bir karar üretmiyordu, hep
# WAIT. Son N kararın TAMAMI WAIT ise ve ai_enabled=true ise, bu "zombi"
# durumu işaretlenir — sistem canlı görünür ama fiilen kör/felçlidir.
_ZOMBIE_WAIT_SAMPLE_SIZE = 30


def _latest_timestamp(table: str, column: str) -> datetime | None:
    with SessionFactory.get_session() as session:
        row = session.execute(text(f"SELECT max({column}) FROM {table}")).scalar()
    return row


def _age_seconds(ts: datetime | None) -> float | None:
    if ts is None:
        return None
    now = datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return (now - ts).total_seconds()


def _check_zombie_wait(ai_enabled: bool) -> dict:
    if not ai_enabled:
        return {"checked": False, "reason": "ai_enabled=false, kontrol atlandı"}

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                "SELECT direction FROM decisions ORDER BY timestamp DESC LIMIT :limit"
            ),
            {"limit": _ZOMBIE_WAIT_SAMPLE_SIZE},
        ).fetchall()

    if len(rows) < _ZOMBIE_WAIT_SAMPLE_SIZE:
        return {"checked": False, "reason": "yeterli geçmiş karar yok (henüz erken)"}

    directions = {(r[0] or "").upper() for r in rows}
    real_directions = directions - {"WAIT", "NEUTRAL", "NO_TRADE", ""}
    return {
        "checked": True,
        "healthy": bool(real_directions),
        "sample_size": len(rows),
        "distinct_directions_seen": sorted(directions),
    }


def check_signal_health() -> dict:
    """Her kritik periyodik modül için: en son gerçek veri ne zaman
    üretildi, eşiği aştı mı. Ayrıca "zombi WAIT" kontrolü — sistem
    çalışıyor görünüp hiç gerçek yönlü karar üretmiyor mu."""
    with SessionFactory.get_session() as session:
        ai_enabled = AppSettingsRepository(session).get("ai_enabled") == "true"

    checks = {}

    candle_age = _age_seconds(_latest_timestamp("market_snapshots", "time"))
    checks["candle_ingestion"] = {
        "age_seconds": candle_age,
        "threshold_seconds": _STALE_THRESHOLDS_SECONDS["candle_ingestion"],
        "healthy": candle_age is not None and candle_age < _STALE_THRESHOLDS_SECONDS["candle_ingestion"],
    }

    order_book_age = _age_seconds(_latest_timestamp("order_book_snapshots", "time"))
    checks["order_book_ingestion"] = {
        "age_seconds": order_book_age,
        "threshold_seconds": _STALE_THRESHOLDS_SECONDS["order_book_ingestion"],
        "healthy": order_book_age is not None and order_book_age < _STALE_THRESHOLDS_SECONDS["order_book_ingestion"],
    }

    cycle_age = _age_seconds(_latest_timestamp("decisions", "timestamp"))
    if ai_enabled:
        cycle_healthy = cycle_age is not None and cycle_age < _STALE_THRESHOLDS_SECONDS["trading_cycle"]
    else:
        cycle_healthy = True  # AI kasıtlı olarak durdurulmuşsa staleness beklenen davranış
    checks["trading_cycle"] = {
        "age_seconds": cycle_age,
        "threshold_seconds": _STALE_THRESHOLDS_SECONDS["trading_cycle"],
        "healthy": cycle_healthy,
        "ai_enabled": ai_enabled,
    }

    checks["zombie_wait"] = _check_zombie_wait(ai_enabled)

    overall_healthy = (
        checks["candle_ingestion"]["healthy"]
        and checks["order_book_ingestion"]["healthy"]
        and checks["trading_cycle"]["healthy"]
        and checks["zombie_wait"].get("healthy", True)
    )

    return {"healthy": overall_healthy, "checks": checks}
