"""Risk Engine testleri – hash doğrulama, secret, limitsiz ret."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.risk import RiskAdjustment, RiskLimitEntry
from engines.risk_engine import RiskEngine


def test_risk_approves_small_position():
    ctx = CognitiveCycleContext(
        risk={"limits": {"max_position_size": RiskLimitEntry(value=1.0)}},
        decision={"proposed_size": 0.5, "proposed_direction": "LONG"},
    )
    engine = RiskEngine()
    result = engine.execute(ctx)
    assert result.risk.evaluation.verdict == "approved"
    assert result.decision.risk_adjusted_size == 0.5

def test_risk_rejects_large_position():
    ctx = CognitiveCycleContext(
        risk={"limits": {"max_position_size": RiskLimitEntry(value=0.3)}},
        decision={"proposed_size": 10.0, "proposed_direction": "LONG"},
    )
    engine = RiskEngine()
    result = engine.execute(ctx)
    assert result.risk.evaluation.verdict == "rejected"

def test_risk_rejects_missing_limit():
    ctx = CognitiveCycleContext(
        risk={"limits": {}},
        decision={"proposed_size": 0.5, "proposed_direction": "LONG"},
    )
    engine = RiskEngine()
    result = engine.execute(ctx)
    assert result.risk.evaluation.verdict == "rejected"
    assert any(r.code == "MISSING_LIMIT" for r in result.risk.evaluation.reasons)

def test_invalid_risk_hash_rejected():
    ctx = CognitiveCycleContext(
        risk={"limits": {"max_position_size": RiskLimitEntry(value=1.0, hash="invalid")}},
        decision={"proposed_size": 0.5, "proposed_direction": "LONG"},
    )
    engine = RiskEngine(secret="supersecret")
    result = engine.execute(ctx)
    assert result.risk.evaluation.verdict == "rejected"
    assert any(r.code == "HASH_MISMATCH" for r in result.risk.evaluation.reasons)

def test_valid_risk_hash_approved():
    import hashlib
    secret = "supersecret"
    valid_hash = hashlib.sha256(f"1.0:{secret}".encode()).hexdigest()
    ctx = CognitiveCycleContext(
        risk={"limits": {"max_position_size": RiskLimitEntry(value=1.0, hash=valid_hash)}},
        decision={"proposed_size": 0.5, "proposed_direction": "LONG"},
    )
    engine = RiskEngine(secret=secret)
    result = engine.execute(ctx)
    assert result.risk.evaluation.verdict == "approved"

def test_risk_factor_only_reduces():
    ctx = CognitiveCycleContext(
        risk={"limits": {"max_position_size": RiskLimitEntry(value=1.0)}, "adjustment": RiskAdjustment(factor=0.5)},
        decision={"proposed_size": 0.5, "proposed_direction": "LONG"},
    )
    engine = RiskEngine()
    result = engine.execute(ctx)
    assert result.decision.risk_adjusted_size == 0.25

def test_risk_factor_cannot_exceed_one():
    ctx = CognitiveCycleContext(
        risk={"limits": {"max_position_size": RiskLimitEntry(value=1.0)}, "adjustment": RiskAdjustment(factor=2.0)},
        decision={"proposed_size": 0.5, "proposed_direction": "LONG"},
    )
    engine = RiskEngine()
    result = engine.execute(ctx)
    assert result.decision.risk_adjusted_size == 0.5

def test_kill_switch_disabled_by_default_zero_threshold():
    """kill_switch_consecutive_losses=0 (varsayılan davranış, icat edilmiş
    bir eşik dayatılmıyor) — consecutive_losses ne olursa olsun devreye
    girmemeli."""
    ctx = CognitiveCycleContext(
        risk={
            "limits": {"max_position_size": RiskLimitEntry(value=1.0)},
            "consecutive_losses": 999,
            "kill_switch_consecutive_losses": 0,
        },
        decision={"proposed_size": 0.5, "proposed_direction": "LONG"},
    )
    engine = RiskEngine()
    result = engine.execute(ctx)
    assert result.risk.evaluation.verdict == "approved"


def test_kill_switch_trips_at_threshold(monkeypatch):
    """Faz 268-sonrası — gerçek olay (2026-08-12): 24 saatte 102 ardışık
    stop-loss, hiçbir otomatik durdurma yoktu. Eşiğe ulaşınca ai_enabled
    GERÇEKTEN false'a çekilmeli (sadece bu cycle'ı reddetmek değil)."""
    captured = {}

    def fake_set(self, key, value, updated_by):
        captured[key] = value

    monkeypatch.setattr(
        "database.repositories.app_settings_repository.AppSettingsRepository.set", fake_set,
    )

    ctx = CognitiveCycleContext(
        risk={
            "limits": {"max_position_size": RiskLimitEntry(value=1.0)},
            "ai_enabled": True,
            "consecutive_losses": 10,
            "kill_switch_consecutive_losses": 10,
        },
        decision={"proposed_size": 0.5, "proposed_direction": "LONG"},
    )
    engine = RiskEngine()
    result = engine.execute(ctx)

    assert result.risk.evaluation.verdict == "rejected"
    assert any(r.code == "CIRCUIT_BREAKER_CONSECUTIVE_LOSSES" for r in result.risk.evaluation.reasons)
    assert result.risk.ai_enabled is False
    assert captured.get("ai_enabled") == "false"


def test_kill_switch_trip_is_recorded_as_a_real_system_event():
    """Faz 269 (Cognitive Core 2.0 / M1) — Veri ve olay altyapısı: bu olay
    şu ana kadar SADECE app_settings.updated_by üzerinden dolaylı
    görülebiliyordu, artık system_events'te sorgulanabilir bir zaman
    çizelgesi girdisi var."""
    from database.repositories.event_log_repository import EventLogRepository
    from database.session_factory import SessionFactory

    ctx = CognitiveCycleContext(
        risk={
            "limits": {"max_position_size": RiskLimitEntry(value=1.0)},
            "ai_enabled": True,
            "consecutive_losses": 17,
            "kill_switch_consecutive_losses": 10,
        },
        decision={"proposed_size": 0.5, "proposed_direction": "LONG"},
    )
    engine = RiskEngine()
    engine.execute(ctx)

    with SessionFactory.get_session() as session:
        events = EventLogRepository(session).list_events(event_type="kill_switch_tripped", limit=5)
    assert len(events) >= 1
    assert events[0]["payload"]["consecutive_losses"] == 17
    assert events[0]["payload"]["threshold"] == 10


def test_kill_switch_trip_event_is_correlated_to_the_triggering_cycle_id():
    """Faz 269-sonrası — distributed tracing: entity_id artık position_
    opened/position_closed ile AYNI desen, hangi cycle'ın bu switch'i
    tetiklediği DB'den doğrudan sorgulanabilir olmalı."""
    from database.repositories.event_log_repository import EventLogRepository
    from database.session_factory import SessionFactory

    ctx = CognitiveCycleContext(
        risk={
            "limits": {"max_position_size": RiskLimitEntry(value=1.0)},
            "ai_enabled": True,
            "consecutive_losses": 25,
            "kill_switch_consecutive_losses": 10,
        },
        decision={"proposed_size": 0.5, "proposed_direction": "LONG"},
    )
    engine = RiskEngine()
    engine.execute(ctx)

    with SessionFactory.get_session() as session:
        events = EventLogRepository(session).list_events(event_type="kill_switch_tripped", limit=5)
    assert events[0]["entity_id"] == str(ctx.cycle_id)


def test_kill_switch_does_not_trip_below_threshold():
    ctx = CognitiveCycleContext(
        risk={
            "limits": {"max_position_size": RiskLimitEntry(value=1.0)},
            "consecutive_losses": 9,
            "kill_switch_consecutive_losses": 10,
        },
        decision={"proposed_size": 0.5, "proposed_direction": "LONG"},
    )
    engine = RiskEngine()
    result = engine.execute(ctx)
    assert result.risk.evaluation.verdict == "approved"


def test_concept_drift_reason_causes_rejection_when_set():
    """Faz 268-sonrası — Concept Drift gate. Gerçek hesaplama (analytics/
    concept_drift.py + iki gerçek zaman penceresi) artık RiskEngine.
    execute()'un İÇİNDE DEĞİL, services/risk_state.py::load_position_
    risk_state()'te yapılıyor (bkz. o dosyadaki test — burada SADECE
    RiskEngine'in ÖNCEDEN hesaplanmış bir concept_drift_reason'ı doğru
    şekilde reddettiğini doğruluyoruz, consecutive_losses testleriyle
    AYNI izole desen — gerçek DB yazımı YOK, kirlenme riski yok)."""
    from contracts.contexts.risk import RiskReason

    ctx = CognitiveCycleContext(
        risk={
            "limits": {"max_position_size": RiskLimitEntry(value=1.0)},
            "concept_drift_reason": RiskReason(
                code="CONCEPT_DRIFT_DEGRADATION", message="test", severity="warning",
            ),
        },
        decision={"proposed_size": 0.5, "proposed_direction": "LONG"},
    )
    result = RiskEngine().execute(ctx)

    assert result.risk.evaluation.verdict == "rejected"
    assert any(r.code == "CONCEPT_DRIFT_DEGRADATION" for r in result.risk.evaluation.reasons)


def test_concept_drift_reason_none_does_not_reject():
    ctx = CognitiveCycleContext(
        risk={
            "limits": {"max_position_size": RiskLimitEntry(value=1.0)},
            "concept_drift_reason": None,
        },
        decision={"proposed_size": 0.5, "proposed_direction": "LONG"},
    )
    result = RiskEngine().execute(ctx)

    assert result.risk.evaluation.verdict == "approved"


def test_modified_value_invalidates_hash():
    """AI limit değerini değiştirirse hash geçersiz olur."""
    import hashlib
    secret = "supersecret"
    # Orijinal limit 1.0 için hash
    valid_hash = hashlib.sha256(f"1.0:{secret}".encode()).hexdigest()

    # Saldırgan değeri 10.0 yapıp hash'i aynı bırakıyor
    ctx = CognitiveCycleContext(
        risk={"limits": {"max_position_size": RiskLimitEntry(value=10.0, hash=valid_hash)}},
        decision={"proposed_size": 5.0, "proposed_direction": "LONG"},
    )
    engine = RiskEngine(secret=secret)
    result = engine.execute(ctx)
    assert result.risk.evaluation.verdict == "rejected"
    assert any(r.code == "HASH_MISMATCH" for r in result.risk.evaluation.reasons)
