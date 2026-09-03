"""Self-Model'in 5 girdisini GERÇEK alt sistemlerden toplayan tek kaynak —
Cognitive Core 3.0. analytics/self_model.py::compute_self_reliability_
snapshot() saf (pure) kalıyor, gerçek veriye dokunan kod burada — hem
canlı API rotası (api/rest/self_model.py) hem haftalık Celery task
(services/tasks.py::refresh_self_model_report_task) AYNI bu fonksiyonu
çağırıyor, iki yerde tekrar yazılmıyor (4 farklı alt sistemi birleştiren
bir toplama mantığı — calibration/feature_ic'in tek-sinyalli, tekrar
yazmaya değer bulunmayan basitliğinden farklı)."""
import time

from sqlalchemy import text

from analytics.backtest_validation import compute_deflated_sharpe_ratio
from analytics.evaluation_cohort import describe_evaluation_window
from analytics.measurement_stability import compute_stability
from analytics.model_drift import compute_feature_drift
from analytics.self_model import compute_self_reliability_snapshot
from database.repositories.calibration_report_repository import CalibrationReportRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET
from services.risk_state import get_concept_drift_diagnostics

_MIN_TRADES_FOR_DSR = 20
STABILITY_LOOKBACK_SNAPSHOTS = 12
_INPUT_STABILITY_FIELDS = ("ece", "recent_dsr")


def _attach_inputs_stability(snapshot: dict, past_snapshots: list[dict]) -> None:
    """Faz 407 — kullanıcı isteği: "ölçtüğümüz her veri için zaman
    içindeki stabilitesini de ölçelim." ECE/DSR'ın haftadan haftaya ne
    kadar tutarlı olduğunu ekliyor — SADECE gözlem, overall_reliability
    sınıflandırmasına hiç dokunmuyor."""
    past_by_field: dict[str, list[float]] = {}
    for snap in past_snapshots:
        snap_inputs = (snap.get("result") or {}).get("inputs") or {}
        for field in _INPUT_STABILITY_FIELDS:
            if snap_inputs.get(field) is not None:
                past_by_field.setdefault(field, []).append(snap_inputs[field])

    snapshot["inputs_stability"] = {
        field: compute_stability([*past_by_field.get(field, []), snapshot["inputs"].get(field)])
        for field in _INPUT_STABILITY_FIELDS
    }


def gather_self_reliability_snapshot() -> dict:
    with SessionFactory.get_session() as session:
        decision_repo = DecisionPersistor(session)
        from database.repositories.self_model_report_repository import SelfModelReportRepository

        past_snapshots = SelfModelReportRepository(session).get_recent(STABILITY_LOOKBACK_SNAPSHOTS)

        # ECE — en son haftalık kalibrasyon raporundan (henüz üretilmediyse
        # None — compute_self_reliability_snapshot None'ı zaten fail-closed
        # ele alıyor, "poor_calibration" bayrağını asla yanlışlıkla basmaz).
        latest_calibration = CalibrationReportRepository(session).get_latest()
        ece = None
        if latest_calibration and latest_calibration.get("result"):
            ece = latest_calibration["result"].get("expected_calibration_error")

        # DSR — GERÇEK kapanmış işlemlerin fiyat-bazlı (kaldıraçsız) yön
        # getirisi (shadow_position_repository.py'deki pnl_pct hesabıyla
        # AYNI formül). pump_fade_v1 hariç — AI'ın karar sisteminden
        # yalıtık, kendi kâr/zarar dağılımı kill switch/concept drift'te
        # olduğu gibi burada da karışmamalı.
        closed_trades = decision_repo.list_closed_trades(
            limit=500, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )
        # Faz 400 — kritik bulgu: bu gatherer DSR'ı besleyen kapanmış-işlem
        # N'ini hiç raporlamıyordu — canonical evaluation cohort görünürlüğü.
        evaluation_window = describe_evaluation_window(
            closed_trades, limit=500, exclude_experiment_buckets=[PUMP_FADE_EXPERIMENT_BUCKET],
        )
        returns = []
        for t in closed_trades:
            entry = t.get("entry_price")
            exit_price = t.get("exit_price")
            direction = t.get("direction")
            if entry and exit_price and direction:
                sign = 1.0 if direction == "LONG" else -1.0
                returns.append(sign * (exit_price - entry) / entry)

        # n_trials — bu canlı sistemin GERÇEK geçmişinde WeightOptimizer'ın
        # ürettiği her ağırlık önerisi (onaylı/reddedilmiş fark etmez, HER
        # biri gerçekten karşılaştırılan bir konfigürasyondu) — küçük
        # gösterip DSR'ı yapay yükseltmemek için mevcut EN GENİŞ gerçek
        # sayı kullanılıyor (bkz. compute_deflated_sharpe_ratio docstring'i).
        n_trials = session.execute(text("SELECT count(*) FROM weight_approvals")).scalar() or 1

        recent_dsr = None
        if len(returns) >= _MIN_TRADES_FOR_DSR:
            dsr_result = compute_deflated_sharpe_ratio(returns, n_trials)
            if dsr_result:
                recent_dsr = dsr_result["deflated_sharpe_ratio"]

        # Feature drift — GERÇEK karar geçmişinden (PSI/KS-test).
        recent_decisions = decision_repo.list_recent(limit=2000)
        drift_report = compute_feature_drift(recent_decisions)
        known_feature_drift_count = sum(
            1 for f in drift_report.values() if f.get("drift_detected")
        )

        # Concept drift — dashboard'un zaten gösterdiği AYNI hesap
        # (services/risk_state.py::get_concept_drift_diagnostics).
        concept_diag = get_concept_drift_diagnostics(decision_repo)
        concept_drift_detected = bool(concept_diag.get("active"))

    # Kill switch — Faz 368 kritik düzeltme: kullanıcı bulgusu (canlı olay,
    # 2026-08-28) — gerçek kill switch tetiklenmiş (ai_enabled=false,
    # updated_by='kill_switch', 11 ardışık kayıpla) ama Self-Model sayfası
    # "hayır" gösteriyordu. Kök neden: eski kod risk_state["consecutive_
    # losses"]'i CANLI yeniden hesaplıyordu (threshold'u GEÇİP GEÇMEDİĞİ,
    # şu anki koşul) — kill switch tetiklendikten SONRA bir kazanç gelip
    # sayaç eşiğin altına (11 -> 1) düşünce, switch HÂLÂ aktifken (ai_
    # enabled hâlâ false, kimse elle açmadı) bu alan yanlışlıkla "hayır"
    # dönüyordu. "kill_switch_active" GERÇEKTEN "şu an durduruldu mu"
    # sorusuna cevap vermeli — koşulun şu an tekrar tetiklenip
    # tetiklenmeyeceğine değil, GERÇEK anahtarın durumuna (ai_enabled +
    # kim/ne değiştirdi) bakılıyor artık.
    with SessionFactory.get_session() as session:
        from database.repositories.app_settings_repository import AppSettingsRepository

        settings_repo = AppSettingsRepository(session)
        ai_enabled = settings_repo.get("ai_enabled")
        ai_enabled_updated_by = settings_repo.get_updated_by("ai_enabled")
    kill_switch_active = ai_enabled == "false" and ai_enabled_updated_by == "kill_switch"

    snapshot = compute_self_reliability_snapshot(
        ece=ece,
        recent_dsr=recent_dsr,
        kill_switch_active=kill_switch_active,
        known_feature_drift_count=known_feature_drift_count,
        concept_drift_detected=concept_drift_detected,
    )
    snapshot["evaluation_window"] = evaluation_window
    _attach_inputs_stability(snapshot, past_snapshots)
    return snapshot


# Faz 310 — kullanıcı isteği: "self modeli karar hattına bağlayalım."
# gather_self_reliability_snapshot() içindeki en pahalı adım
# (known_feature_drift_count -> compute_feature_drift, 2000 kararlık
# PSI/KS-test) bir trading cycle'ında watchlist'teki HER sembol için
# MetaStage'den çağrılırsa tekrar tekrar (sembol başına bir kez)
# çalışırdı — market_data/onchain/onchain_provider.py::_cached() ile
# AYNI disiplin: kısa bir TTL'lik önbellek, bir cycle içindeki tüm
# sembollerin AYNI anlık görüntüyü paylaşmasını sağlıyor.
_SNAPSHOT_CACHE_TTL_SECONDS = 1800
_snapshot_cache: tuple[float, dict] | None = None


def get_cached_self_reliability_snapshot() -> dict:
    """MetaStage'in (engines/cognitive_pipeline.py) çağırdığı, TTL'li
    önbellekli sürüm — canlı API rotası/haftalık Celery task hâlâ taze
    gather_self_reliability_snapshot()'ı doğrudan kullanıyor, bu SADECE
    yüksek frekanslı karar hattı için."""
    global _snapshot_cache
    now = time.monotonic()
    if _snapshot_cache is not None and (now - _snapshot_cache[0]) < _SNAPSHOT_CACHE_TTL_SECONDS:
        return _snapshot_cache[1]
    snapshot = gather_self_reliability_snapshot()
    _snapshot_cache = (now, snapshot)
    return snapshot
