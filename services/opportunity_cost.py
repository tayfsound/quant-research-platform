"""Path‑Aware Opportunity Cost — min_significant_r, exit_price düzeltmesi."""
import math
from contracts.opportunity import OpportunityCost
from contracts.context import CognitiveCycleContext

class OpportunityCostCalculator:
    def __init__(self, initial_risk: float = 100.0, min_significant_r: float = 0.5):
        self.initial_risk = initial_risk
        self.min_significant_r = min_significant_r

    def _compute_r_multiple(
        self,
        direction: str,
        entry: float,
        stop_loss: float | None,
        high: float,
        low: float,
        price_path: list[float] | None = None,
    ) -> tuple[float, float, bool]:
        risk = abs(entry - stop_loss) if stop_loss else self.initial_risk
        if risk <= 0:
            return 0.0, 0.0, False

        if direction == "LONG":
            mfe_r = (high - entry) / risk
            mae_r = (entry - low) / risk
        else:
            mfe_r = (entry - low) / risk
            mae_r = (high - entry) / risk

        stop_hit = False
        if price_path and stop_loss:
            if direction == "LONG":
                stop_hit = any(p <= stop_loss for p in price_path)
            else:
                stop_hit = any(p >= stop_loss for p in price_path)

        return mfe_r, mae_r, stop_hit

    def evaluate_wait(
        self,
        ctx: CognitiveCycleContext,
        entry: float,
        stop_loss: float | None,
        high: float,
        low: float,
        holding_minutes: int,
        price_path: list[float] | None = None,
    ) -> OpportunityCost:
        direction = ctx.decision.proposed_direction
        mfe_r, mae_r, stop_hit = self._compute_r_multiple(
            direction, entry, stop_loss, high, low, price_path,
        )

        if stop_hit:
            wait_correct = True
            missed_r = 0.0
        elif mfe_r > max(mae_r, 0) and mfe_r > self.min_significant_r:
            wait_correct = False
            missed_r = mfe_r
        else:
            wait_correct = True
            missed_r = 0.0

        return OpportunityCost(
            symbol=ctx.market.symbol,
            decision="WAIT",
            direction=direction,
            entry_price=entry,
            exit_price=0.0,
            highest_price=high,
            lowest_price=low,
            max_favorable_excursion=round(mfe_r, 3),
            max_adverse_excursion=round(mae_r, 3),
            holding_period_minutes=holding_minutes,
            missed_r_multiple=round(missed_r, 3),
            wait_was_correct=wait_correct,
            confidence_at_decision=ctx.decision.confidence,
        )

    def evaluate_exit(
        self,
        ctx: CognitiveCycleContext,
        exit_price: float,
        entry: float,
        stop_loss: float | None,
        high_after_exit: float,
        low_after_exit: float,
        holding_minutes: int,
    ) -> OpportunityCost:
        direction = ctx.decision.proposed_direction
        mfe_r, mae_r, _ = self._compute_r_multiple(
            direction, exit_price, stop_loss, high_after_exit, low_after_exit,
        )

        early_exit = mfe_r > max(mae_r, 0) and mfe_r > self.min_significant_r
        missed_r = mfe_r if early_exit else 0.0
        wait_correct = not early_exit

        return OpportunityCost(
            symbol=ctx.market.symbol,
            decision="EXIT",
            direction=direction,
            entry_price=entry,
            exit_price=exit_price,
            highest_price=high_after_exit,
            lowest_price=low_after_exit,
            max_favorable_excursion=round(mfe_r, 3),
            max_adverse_excursion=round(mae_r, 3),
            holding_period_minutes=holding_minutes,
            missed_r_multiple=round(missed_r, 3),
            wait_was_correct=wait_correct,
            confidence_at_decision=ctx.decision.confidence,
        )

    def evaluate_reduce(
        self,
        ctx: CognitiveCycleContext,
        reduce_price: float,
        entry: float,
        stop_loss: float | None,
        high_after_reduce: float,
        low_after_reduce: float,
        holding_minutes: int,
    ) -> OpportunityCost:
        cost = self.evaluate_exit(
            ctx, reduce_price, entry, stop_loss,
            high_after_reduce, low_after_reduce, holding_minutes,
        )
        cost.decision = "REDUCE"
        cost.missed_r_multiple = round(cost.missed_r_multiple * 0.5, 3)
        return cost
