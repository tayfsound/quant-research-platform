"""Faz 362-devam — Belief Reversal Exit.

Kullanıcı fikri (2026-08-24): "council'in fikir değiştirmesi önemli veri
— elimde açık bir pozisyon varken council art arda tersine dönerse buna
tepki vermemiz lazım." İlk (dar, 4 günlük, n<=27) ölçüm net bir "HAYIR"
vermişti — ama kullanıcı bunun küçük örneklem sorunu olabileceğini
sorguladı ve haklı çıktı: geniş pencerede (10-24 Ağustos, 3619 pozisyon,
bkz. analytics/signal_persistence.py başlığındaki tam tablo) N=6 ardışık
onaylı (confidence>=0.65) tersine dönüşte sonuç %89 "daha iyi olurdu",
felaket boyutlu uç değerler (N<=4'te -$800'e varan "tutmak çok daha
iyiydi" vakaları) tamamen kayboluyor.

services/regime_reversal_guardian.py (Faz 352) ile AYNI mimari (stateless
— hiçbir "tetiklendi" bayrağı persiste edilmiyor, her sweep taze
hesaplıyor; kapanış primitifi close_partial ile AYNI, zaten üretimde
kanıtlanmış) — ama regime_reversal_guardian YÖN-bazlı (bir yönün GENEL
ardışık stop sayısı), bu modül SEMBOL-bazlı (o sembolde council'in
GÜNCEL, ters yönlü inancı) çalışıyor — farklı, tamamlayıcı bir sinyal."""
import structlog

logger = structlog.get_logger()

_MECHANICAL_EXPERIMENT_BUCKETS = {"pump_fade_v1", "basis_arb_v1"}


def _load_settings() -> tuple[bool, int, float]:
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        enabled = repo.get("belief_reversal_exit_enabled") == "true"
        min_cycles = int(repo.get("belief_reversal_exit_min_consistent_cycles"))
        min_confidence = float(repo.get("belief_reversal_exit_min_confidence"))
    return enabled, min_cycles, min_confidence


def find_reversal_triggered_positions(min_cycles: int, min_confidence: float) -> list[dict]:
    """GERÇEK açık pozisyonları (mekanik stratejiler hariç — kendi risk
    yönetimlerine sahipler, council'in yön değiştirmesi onları
    etkilemiyor) tarar, her biri için o sembolün son `min_cycles`
    kararının TAMAMI pozisyonun tersine VE yeterince güvenli mi diye
    bakar (bkz. analytics/signal_persistence.py::consecutive_reversal_
    run_length). Tetiklenenleri döner — kapatma İÇERMİYOR (saf tarama,
    test edilebilir)."""
    from analytics.signal_persistence import consecutive_reversal_run_length, is_belief_reversal_exit_triggered
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        positions = persistor.list_open_positions(limit=None)
        positions = [
            p for p in positions
            if p.get("experiment_bucket") not in _MECHANICAL_EXPERIMENT_BUCKETS
            and (p.get("direction") or "").upper() in ("LONG", "SHORT")
        ]
        triggered = []
        for pos in positions:
            prior = persistor.list_recent_direction_confidence_for_symbol(
                pos["symbol"], limit=min_cycles, since=pos.get("opened_at")
            )
            run_length = consecutive_reversal_run_length(prior, pos["direction"].upper(), min_confidence)
            if is_belief_reversal_exit_triggered(run_length, min_cycles):
                triggered.append({**pos, "reversal_run_length": run_length})
    return triggered


def sweep_reversal_exits() -> dict:
    """Periyodik Celery görevinden çağrılır (bkz. services/tasks.py::
    belief_reversal_exit_task). Kapalıyken sıfır maliyetli no-op —
    idempotent: zaten kapatılmış pozisyonlar için tekrar çağrılması
    zararsız (list_open_positions zaten kapananları döndürmez)."""
    enabled, min_cycles, min_confidence = _load_settings()
    if not enabled:
        return {"enabled": False}

    triggered = find_reversal_triggered_positions(min_cycles, min_confidence)
    if not triggered:
        return {"enabled": True, "min_cycles": min_cycles, "min_confidence": min_confidence, "closed": []}

    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory
    from market_data.ingestion.data_provider import RoutingProvider
    from services.position_closer import PositionCloser

    closer = PositionCloser(RoutingProvider())
    closed = []
    for pos in triggered:
        with SessionFactory.get_session() as session:
            try:
                result = closer.close_partial(DecisionPersistor(session), str(pos["id"]), 1.0)
            except ValueError:
                continue
        closed.append({
            "symbol": pos["symbol"], "direction": pos["direction"],
            "reversal_run_length": pos["reversal_run_length"], "pnl": result["pnl"],
        })

    if closed:
        logger.warning("belief_reversal_exit_triggered", min_cycles=min_cycles, closed_count=len(closed))

    return {
        "enabled": True, "min_cycles": min_cycles, "min_confidence": min_confidence,
        "triggered_count": len(triggered), "closed": closed,
    }
