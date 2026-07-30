"""Observation Pipeline — UCEL binding ile."""
from contracts.context import CognitiveCycleContext
from contracts.observation import Observation, ObservationType
from services.cognitive_binder import CognitiveBinder


class ObservationPipeline:
    def __init__(self):
        self.binder = CognitiveBinder()

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        # Ham veriden gözlem üret
        obs = Observation(
            type=ObservationType.INDICATOR,
            symbol=ctx.market.symbol,
            timeframe=ctx.market.timeframe,
            description=f"RSI={ctx.market.features.get('RSI', 0)}",
            data=ctx.market.features,
        )
        # UCEL binding oluştur
        binding = self.binder.bind_observation(obs)
        if binding:
            ctx.cognition.relevant_knowledge.append({
                "type": "cognitive_binding",
                "data": binding.model_dump(),
            })
        ctx.cognition.relevant_knowledge.append({
            "type": "observation",
            "data": obs.model_dump(),
        })
        return ctx
