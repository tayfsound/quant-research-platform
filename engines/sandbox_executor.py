"""Sandbox Executor — sanal portföy ile limitsiz deney."""
from contracts.context import CognitiveCycleContext
from contracts.observation import Observation, ObservationType


class VirtualPortfolio:
    def __init__(self, initial_balance: float = 10000.0):
        self.balance = initial_balance
        self.positions: dict[str, float] = {}
        self.trades: list[dict] = []

    def execute(self, symbol: str, direction: str, size: float, price: float) -> dict:
        cost = size * price
        if direction == "LONG":
            self.balance -= cost
            self.positions[symbol] = self.positions.get(symbol, 0) + size
        else:
            self.balance += cost
            self.positions[symbol] = self.positions.get(symbol, 0) - size
        trade = {"symbol": symbol, "direction": direction, "size": size, "price": price, "balance": self.balance}
        self.trades.append(trade)
        return trade

class SandboxExecutor:
    def __init__(self):
        self.portfolio = VirtualPortfolio()

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        result = self.portfolio.execute(
            symbol=ctx.market.symbol,
            direction=ctx.decision.proposed_direction,
            size=ctx.decision.proposed_size,
            price=ctx.market.features.get("price", 0.0),
        )
        obs = Observation(
            type=ObservationType.EXPERIMENT,
            symbol=ctx.market.symbol,
            timeframe=ctx.market.timeframe,
            description=f"Sandbox: {result}",
            data={"mode": "experiment", "result": result},
        )
        ctx.cognition.relevant_knowledge.append({"type": "experiment", "data": obs.model_dump()})
        ctx.outcome = {"executed": True, "mode": "sandbox", "portfolio": {"balance": self.portfolio.balance}}
        return ctx
