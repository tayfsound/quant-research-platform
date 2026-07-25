"""Decision Audit testleri."""
from datetime import datetime
from uuid import uuid4

from contracts.decision_audit import DecisionAuditRecord, ModelOutput


def test_create_audit_record():
    record = DecisionAuditRecord(
        timestamp=datetime.now(),
        symbol="BTCUSDT",
        market_snapshot_ref=uuid4(),
        feature_vector_ref=uuid4(),
        final_direction="LONG",
        final_size=0.5,
        prompt_hash="abc123",
        system_version="0.15.5",
    )
    assert record.symbol == "BTCUSDT"
    assert record.schema_version == 3

def test_model_output():
    output = ModelOutput(
        agent_id=uuid4(),
        direction="LONG",
        confidence=0.85,
        latency_ms=120,
        model_version="xgboost_v2",
    )
    assert output.confidence == 0.85
