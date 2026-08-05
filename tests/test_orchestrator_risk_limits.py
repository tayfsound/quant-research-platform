"""Gap #15 follow-up: the first pass only fixed api/rest/cognitive.py's
context construction. CognitiveOrchestrator.run_cycle() — the actually
heavily-used path behind /orchestrator/cycle and /dashboard/latest — had
the exact same bug independently (its own empty CognitiveCycleContext(),
never touching ctx.risk.limits), found by tracing where else RiskEngine
gets called with a context nobody populated limits on."""
from datetime import datetime, UTC
from uuid import uuid4

from database.repositories.risk_limit_repository import RiskLimitModel, RiskLimitRepository
from database.session_factory import SessionFactory
from services.orchestrator import CognitiveOrchestrator


def test_orchestrator_run_cycle_picks_up_db_backed_risk_limit():
    with SessionFactory.get_session() as session:
        RiskLimitRepository(session).save(RiskLimitModel(
            id=uuid4(),
            scope="global",
            limit_type="max_position_size",
            value=1.0,
            hash="",
            created_by="test",
            created_at=datetime.now(UTC),
        ))

    result = CognitiveOrchestrator().run_cycle(seed=7)

    assert "MISSING_LIMIT" not in result["risk_reasons"]
