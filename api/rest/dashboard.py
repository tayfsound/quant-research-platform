"""Dashboard API."""
from fastapi import APIRouter, Depends

from contracts.auth import Role
from services.auth_service import AuthContext, get_current_user, require_role
from services.orchestrator import CognitiveOrchestrator

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
_orch = CognitiveOrchestrator()

@router.get("/latest")
def latest_cycle(user: AuthContext = Depends(require_role(Role.OPERATOR))):
    result = _orch.run_cycle(seed=42)
    return {
        "direction": result.get("direction"),
        "pnl": result.get("pnl"),
        "win": result.get("win"),
        "risk_verdict": result.get("risk_verdict"),
        "memory_size": result.get("memory_size"),
    }

@router.get("/health")
def health(user: AuthContext = Depends(get_current_user)):
    return {"status": "ok", "tests": 222}


@router.get("/concept-drift-status")
def concept_drift_status(user: AuthContext = Depends(get_current_user)):
    """Faz 268-sonrası — kullanıcı isteği: "Concept Drift aktif olduğunda
    panelden göreyim, sistem neden pozisyon almıyor bilmeden kalmayayım."
    Aynı eşiği/hesabı kullanır (services/risk_state.py::get_concept_
    drift_diagnostics) — RiskEngine'in ne yaptığıyla dashboard'un
    gösterdiği HER ZAMAN aynı, ayrı bir kopya hesap değil."""
    from datetime import datetime

    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory
    from services.risk_state import get_concept_drift_diagnostics

    with SessionFactory.get_session() as session:
        settings_repo = AppSettingsRepository(session)
        # Faz 383 — RiskEngine'in GERÇEKTE ne uyguladığıyla (bkz. risk_
        # state.py::load_position_risk_state) AYNI cutoff — aksi halde
        # kullanıcı "sıfırla" dedikten sonra panel hâlâ eski/kirlenmiş
        # pencereyle "aktif" gösterebilirdi, tek gerçek kaynak ilkesi bozulur.
        legacy_cutoff_raw = settings_repo.get("concept_drift_legacy_cutoff_at")
        legacy_cutoff_at = datetime.fromisoformat(legacy_cutoff_raw) if legacy_cutoff_raw else None
        diagnostics = get_concept_drift_diagnostics(DecisionPersistor(session), min_opened_at=legacy_cutoff_at)
        # Faz 268-sonrası: kullanıcı isteği — koruma sadece canlı modda
        # pozisyon açmayı engelliyor (bkz. services/risk_state.py::
        # load_position_risk_state). Panel istatistikleri hep gerçek
        # gösterir ama "enforced" olmadan bu SADECE bilgilendirme, sistem
        # gerçekte durdurulmuş değil.
        trading_mode = settings_repo.get("trading_mode")
        diagnostics["enforced"] = trading_mode == "live"
        diagnostics["reset_at"] = legacy_cutoff_raw
        return diagnostics


@router.post("/concept-drift-status/reset")
def reset_concept_drift(user: AuthContext = Depends(require_role(Role.OPERATOR))):
    """Faz 383 — kullanıcı isteği: "tetiklendi diye sonsuza kadar
    bırakacak değiliz, dashboard'daki uyarı balonuna kapatma butonu
    gelsin." Bu, eski kötü işlemleri SİLMİYOR/GİZLEMİYOR — sadece Concept
    Drift'in bakma penceresini "şu andan itibaren"e çeviriyor (bkz.
    services/risk_state.py::get_concept_drift_diagnostics docstring'i —
    kill_switch_legacy_cutoff_at ile AYNI, zaten kanıtlanmış desen).
    Performans gerçekten düzelmediyse, yeterli taze veri birikince drift
    dürüstçe TEKRAR tetiklenir — bu kalıcı bir susturma değil."""
    from datetime import UTC, datetime

    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    now = datetime.now(UTC)
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set(
            "concept_drift_legacy_cutoff_at", now.isoformat(), updated_by=user.username,
        )
    return {"reset_at": now.isoformat(), "reset_by": user.username}


@router.get("/market-direction-summary")
def market_direction_summary(user: AuthContext = Depends(get_current_user)):
    """Faz 362-devam — backlog madde 21, kullanıcı isteği: "AI şu an
    piyasa yönünü nasıl görüyor" bilgi kartı — mevcut ortalama/dominant
    belief.direction'ın canlı özeti. Her sembolün EN SON kararının
    (status'tan bağımsız, council'in o anki ham eğilimi) yön/confidence'ı
    üzerinden — 24 saatten eski, taranmamış/stale sembolleri hariç
    tutuyor (aksi halde uzun süre işlem görmemiş bir sembolün eski
    yönü, güncel bir sinyalmiş gibi ortalamayı kirletirdi)."""
    from datetime import UTC, datetime, timedelta

    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    since = datetime.now(UTC) - timedelta(hours=24)
    with SessionFactory.get_session() as session:
        rows = DecisionPersistor(session).latest_direction_confidence_by_symbol(since=since)

    long_rows = [r for r in rows if r["direction"] == "LONG"]
    short_rows = [r for r in rows if r["direction"] == "SHORT"]
    wait_rows = [r for r in rows if r["direction"] not in ("LONG", "SHORT")]
    total = len(rows)

    def _avg_confidence(lst: list[dict]) -> float | None:
        if not lst:
            return None
        return sum(r["confidence"] or 0.0 for r in lst) / len(lst)

    def _top(lst: list[dict], n: int = 5) -> list[dict]:
        ranked = sorted(lst, key=lambda r: r["confidence"] or 0.0, reverse=True)[:n]
        return [{"symbol": r["symbol"], "confidence": r["confidence"]} for r in ranked]

    counts = {"LONG": len(long_rows), "SHORT": len(short_rows), "WAIT": len(wait_rows)}
    dominant_direction = max(counts, key=counts.get) if total else None

    return {
        "as_of": datetime.now(UTC).isoformat(),
        "symbol_count": total,
        "long_count": len(long_rows),
        "short_count": len(short_rows),
        "wait_count": len(wait_rows),
        "long_pct": (len(long_rows) / total) if total else None,
        "short_pct": (len(short_rows) / total) if total else None,
        "wait_pct": (len(wait_rows) / total) if total else None,
        "dominant_direction": dominant_direction,
        "avg_confidence_long": _avg_confidence(long_rows),
        "avg_confidence_short": _avg_confidence(short_rows),
        "top_long_symbols": _top(long_rows),
        "top_short_symbols": _top(short_rows),
    }


@router.get("/asset-class-performance")
def asset_class_performance_summary(user: AuthContext = Depends(get_current_user)):
    """Kullanıcı isteği (2026-08-27): "Bitcoin/Emtia/Hisse performansını
    dashboard bilgilendirme kartı olarak görmek istiyorum... hangi işlem
    türünde AI ne kadar başarılı." services/asset_class_performance_
    gatherer.py'nin gerçek kapanmış işlemlerden hesapladığı sonucu
    doğrudan döner."""
    from services.asset_class_performance_gatherer import gather_asset_class_performance

    return gather_asset_class_performance()


@router.get("/regime-performance")
def regime_performance_summary(user: AuthContext = Depends(get_current_user)):
    """Kullanıcı isteği (2026-08-27): "REJİME GÖRE AI KONSEYİ GİRİŞLERİ
    kartındaki butonlara hangi rejimin ne kadar başarılı olduğu
    bilgisini ekleyelim." services/regime_performance_gatherer.py'nin
    gerçek kapanmış işlemlerden hesapladığı sonucu doğrudan döner."""
    from services.regime_performance_gatherer import gather_regime_performance

    return gather_regime_performance()
