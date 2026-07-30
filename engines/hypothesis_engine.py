"""Hypothesis Engine — önce topla, sonra ekle."""
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from services.cognitive_binder import CognitiveBinder


class HypothesisEngine:
    def __init__(self):
        self.binder = CognitiveBinder()
        self._hypotheses: list[dict] = []

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        beliefs = list(ctx.cognition.active_beliefs)  # kopya al
        for belief_data in beliefs:
            belief = Belief(**belief_data) if isinstance(belief_data, dict) else belief_data
            hypothesis = self.binder.belief_to_hypothesis(belief)
            self._hypotheses.append(hypothesis.model_dump())
        ctx.cognition.active_hypotheses = self._hypotheses
        return ctx
