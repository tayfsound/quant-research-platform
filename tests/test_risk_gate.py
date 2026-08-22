"""RiskGateStage integration tests."""
from unittest.mock import MagicMock

from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from engines.cognitive_pipeline import RiskGateStage


class FakeLimit:
    value = 0.5

class FakeEval:
    verdict = ""
    reasons = []

def test_rejects_oversized():
    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.final_size = 1.0
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0

    ctx = stage.execute(ctx)

    assert ctx.decision.action == ActionType.WAIT
    assert ctx.decision.final_size == 0.0
    assert ctx.risk.evaluation.verdict == "rejected"
    assert any(r.code == "POST_FUSION_SIZE_EXCEEDED" for r in ctx.risk.evaluation.reasons)

def test_approves_valid():
    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.final_size = 0.3
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "approved"
    assert ctx.decision.final_size == 0.3


def test_does_not_bypass_checks_in_test_mode():
    """Faz 268-sonrası — kritik bulgu: Faz 262 bu bypass'ı RiskEngine.
    execute() (ön kapı) için kaldırmıştı ("test modu artık live modla
    AYNI kuralları uyguluyor") ama RiskGateStage (son kapı) hâlâ
    trading_mode='test' iken TÜM kontrolleri atlıyordu — gerçek olayda
    (XAUTUSDT SHORT x54) bu son kapı hiç devreye girmemişti."""
    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "test"
    ctx.decision.final_size = 1.0
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "rejected"
    assert any(r.code == "POST_FUSION_SIZE_EXCEEDED" for r in ctx.risk.evaluation.reasons)


def test_rejects_when_too_many_same_direction_positions_already_open_on_symbol():
    """Faz 268-sonrası — gerçek olay: XAUTUSDT'de aynı yönde (SHORT) 54
    pozisyon aynı anda açık kalabilmişti — max_concurrent_positions
    TOPLAM sayıya bakıyor, bu sembol/yön kombinasyonuna hiç bakmıyordu."""
    from contracts.contexts.decision import ActionType

    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.action = ActionType.ENTER_SHORT
    ctx.decision.final_size = 0.1
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0
    ctx.risk.same_direction_open_counts = {"SHORT": 5, "LONG": 0}
    ctx.risk.max_open_positions_per_symbol_direction = 5

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "rejected"
    assert any(r.code == "MAX_SAME_SYMBOL_DIRECTION_POSITIONS" for r in ctx.risk.evaluation.reasons)


def test_approves_when_same_direction_open_count_is_below_the_limit():
    from contracts.contexts.decision import ActionType

    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.action = ActionType.ENTER_SHORT
    ctx.decision.final_size = 0.1
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0
    ctx.risk.same_direction_open_counts = {"SHORT": 2, "LONG": 0}
    ctx.risk.max_open_positions_per_symbol_direction = 5

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "approved"


def test_same_direction_cap_disabled_when_setting_is_none():
    from contracts.contexts.decision import ActionType

    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.action = ActionType.ENTER_SHORT
    ctx.decision.final_size = 0.1
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0
    ctx.risk.same_direction_open_counts = {"SHORT": 999, "LONG": 0}
    ctx.risk.max_open_positions_per_symbol_direction = None

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "approved"
