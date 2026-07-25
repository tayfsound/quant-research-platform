"""Path‑Aware Opportunity Cost testleri."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import Decision, ActionType
from services.opportunity_cost import OpportunityCostCalculator

def test_long_wait_stop_would_hit():
    calc = OpportunityCostCalculator(initial_risk=100)
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT"},
        decision=Decision(proposed_direction="LONG", action=ActionType.WAIT),
    )
    # Stop-loss 49500, fiyat 49000'e düştü → stop tetiklenirdi
    cost = calc.evaluate_wait(
        ctx, entry=50000, stop_loss=49500,
        high=51000, low=49000, holding_minutes=60,
        price_path=[50000, 49800, 49500, 49000],
    )
    assert cost.wait_was_correct is True
    assert cost.missed_r_multiple == 0.0

def test_long_wait_opportunity_missed_no_stop_hit():
    calc = OpportunityCostCalculator(initial_risk=100)
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT"},
        decision=Decision(proposed_direction="LONG", action=ActionType.WAIT),
    )
    cost = calc.evaluate_wait(
        ctx, entry=50000, stop_loss=49500,
        high=55000, low=49800, holding_minutes=60,
        price_path=[50000, 50500, 52000, 55000],
    )
    assert cost.wait_was_correct is False
    assert cost.missed_r_multiple > 0

def test_exit_early_evaluation():
    calc = OpportunityCostCalculator(initial_risk=100)
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT"},
        decision=Decision(proposed_direction="LONG", action=ActionType.EXIT),
    )
    cost = calc.evaluate_exit(
        ctx, exit_price=51000, entry=50000, stop_loss=49500,
        high_after_exit=55000, low_after_exit=50500, holding_minutes=60,
    )
    assert cost.missed_r_multiple > 0  # Erken çıkış
    assert cost.wait_was_correct is False
