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


def test_concept_drift_rejects_when_recent_win_rate_drops_significantly_and_meaningfully():
    """Faz 268-sonrası — Concept Drift gate: iki GERÇEK zaman penceresi
    arasında kazanma oranı hem istatistiksel olarak anlamlı (p<0.05) HEM
    DE büyük (>=15 puan) düşerse reddedilmeli. "far future" zaman damgası
    kullanılıyor (test_risk_state.py'deki AYNI desen) — bu satırlar
    list_closed_trades()'in (closed_at DESC) en önünde garanti çıksın,
    paylaşılan test DB'sindeki başka gerçek kayıtlarla karışmasın."""
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from contracts.decision_event import DecisionEvent
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    symbol = f"RISKENGINE{uuid4().hex[:8]}"
    far_future = datetime.now(UTC) + timedelta(days=3650, hours=5)
    try:
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            # Baseline (100 kayıt, DAHA ESKİ -> daha erken closed_at): %90 kazanç.
            for i in range(100):
                pnl = 10.0 if i % 10 != 0 else -5.0  # %90 kazanç
                event = DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                )
                repo.persist(event)
                repo.close_position(
                    decision_id=str(event.id), exit_price=100.0, pnl=pnl,
                    closed_at=far_future + timedelta(seconds=i),
                )
            # Recent (50 kayıt, DAHA YENİ -> daha geç closed_at): %20 kazanç.
            for i in range(50):
                pnl = 10.0 if i % 5 == 0 else -5.0  # %20 kazanç
                event = DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                )
                repo.persist(event)
                repo.close_position(
                    decision_id=str(event.id), exit_price=100.0, pnl=pnl,
                    closed_at=far_future + timedelta(hours=1, seconds=i),
                )

        ctx = CognitiveCycleContext(
            risk={"limits": {"max_position_size": RiskLimitEntry(value=1.0)}},
            decision={"proposed_size": 0.5, "proposed_direction": "LONG"},
        )
        result = RiskEngine().execute(ctx)

        assert result.risk.evaluation.verdict == "rejected"
        assert any(r.code == "CONCEPT_DRIFT_DEGRADATION" for r in result.risk.evaluation.reasons)
    finally:
        with SessionFactory.get_session() as session:
            session.execute(
                __import__("sqlalchemy").text("DELETE FROM decisions WHERE symbol LIKE :p"),
                {"p": f"{symbol}%"},
            )
            session.commit()


def test_concept_drift_does_not_reject_when_recent_win_rate_stays_similar():
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from contracts.decision_event import DecisionEvent
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    symbol = f"RISKENGINE{uuid4().hex[:8]}"
    far_future = datetime.now(UTC) + timedelta(days=3650, hours=6)
    try:
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            # Baseline VE recent AYNI (~%60 kazanç) -> gerçek bir drift yok.
            for i in range(150):
                pnl = 10.0 if i % 5 < 3 else -5.0  # %60 kazanç
                event = DecisionEvent(
                    id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                    final_size=1.0, status="open", entry_price=100.0, quantity=1.0,
                )
                repo.persist(event)
                repo.close_position(
                    decision_id=str(event.id), exit_price=100.0, pnl=pnl,
                    closed_at=far_future + timedelta(seconds=i),
                )

        ctx = CognitiveCycleContext(
            risk={"limits": {"max_position_size": RiskLimitEntry(value=1.0)}},
            decision={"proposed_size": 0.5, "proposed_direction": "LONG"},
        )
        result = RiskEngine().execute(ctx)

        assert result.risk.evaluation.verdict == "approved"
    finally:
        with SessionFactory.get_session() as session:
            session.execute(
                __import__("sqlalchemy").text("DELETE FROM decisions WHERE symbol LIKE :p"),
                {"p": f"{symbol}%"},
            )
            session.commit()


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
