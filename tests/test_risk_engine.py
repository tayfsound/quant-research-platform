"""Risk Engine testleri – hash doğrulama, secret, limitsiz ret."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.risk import RiskLimitEntry, RiskAdjustment
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
