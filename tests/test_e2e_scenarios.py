"""Roadmap Sprint 1: guardrail-red / outcome-none / outcome-var against a real DB.

Unlike test_e2e_persist_chain.py (which mocks the persistor and belief store),
these exercise the real DecisionPersistor/Postgres session and real
LearningLoop.agent_memory, so the DB row and the learning side effect are
both genuinely proven, not asserted against a mock.
"""
from unittest.mock import patch

from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory


class FakeLimit:
    value = 10.0

    def verify(self, secret):
        return True


def _engine():
    from services.cognitive_engine import CognitiveEngine
    return CognitiveEngine()


def _base_ctx(symbol="BTCUSDT"):
    from contracts.context import CognitiveCycleContext
    ctx = CognitiveCycleContext()
    ctx.market.symbol = symbol
    ctx.decision.proposed_direction = "LONG"
    ctx.decision.confidence = 0.8
    ctx.risk.current_drawdown = 0.0
    return ctx


def _fetch_decision(decision_id) -> dict | None:
    with SessionFactory.get_session() as session:
        return DecisionPersistor(session).get_by_id(str(decision_id))


def test_guardrail_red_rejects_pre_fusion_real_db():
    """No max_position_size limit -> GuardrailStage rejects before Council/Fusion even run."""
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            engine = _engine()
            ctx = _base_ctx()
            ctx.decision.proposed_size = 1.0
            ctx.risk.limits = {}  # no max_position_size -> RiskEngine MISSING_LIMIT

            with patch.object(engine, "council_stage") as mock_council:
                ctx = engine.run(ctx, persist=True)
                mock_council.execute.assert_not_called()

            assert ctx.decision.action.value == "WAIT"
            assert ctx.decision.final_size == 0.0
            assert ctx.risk.evaluation.verdict == "rejected"
            assert any(r.code == "MISSING_LIMIT" for r in ctx.risk.evaluation.reasons)

            row = _fetch_decision(ctx.cycle_id)
            assert row is not None
            assert float(row["size"]) == 0.0
            assert row["direction"] == "LONG"


def test_outcome_none_learning_is_noop_real_db():
    """Decision persisted for real, no outcome ever attached -> learning never fires."""
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            engine = _engine()
            ctx = _base_ctx()
            ctx.decision.proposed_size = 0.3
            ctx.risk.limits = {"max_position_size": FakeLimit()}

            with patch.object(engine.learning_loop, "record") as mock_record:
                ctx = engine.run(ctx, persist=True)
                mock_record.assert_not_called()

            row = _fetch_decision(ctx.cycle_id)
            assert row is not None  # decision itself IS recorded


def test_outcome_var_triggers_agent_memory_update_real_db():
    """run(persist=False) -> attach outcome -> finalize(): one real DB row + real learning side effect."""
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from contracts.outcome import TradeOutcome

            engine = _engine()
            ctx = _base_ctx()
            ctx.decision.proposed_size = 0.3
            ctx.risk.limits = {"max_position_size": FakeLimit()}

            ctx = engine.run(ctx, persist=False)
            row_before_finalize = _fetch_decision(ctx.cycle_id)
            assert row_before_finalize is None  # persist=False -> nothing written yet

            ctx.outcome = TradeOutcome(
                pnl=42.0, win=True, decision="LONG", confidence_at_decision=0.8,
            )

            real_record = engine.learning_loop.agent_memory.record
            with patch.object(
                engine.learning_loop.agent_memory, "record", wraps=real_record
            ) as spy_record:
                engine.finalize(ctx)
                spy_record.assert_called()

            row = _fetch_decision(ctx.cycle_id)
            assert row is not None
            assert str(row["id"]) == str(ctx.cycle_id)
