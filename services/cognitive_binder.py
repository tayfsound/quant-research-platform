"""Cognitive Binder — Observation → Knowledge → Belief → Hypothesis döngüsünü UCEL ile bağlar."""
from contracts.belief import Belief
from contracts.cognitive_binding import CognitiveBinding
from contracts.expression import Comparison, Constant, Expression, OpType, Variable
from contracts.hypothesis import Hypothesis
from contracts.knowledge import KnowledgeCategory, KnowledgeEntry
from contracts.observation import Observation, ObservationType


class CognitiveBinder:
    """UCEL tabanlı bilişsel bağlayıcı."""

    def bind_observation(self, obs: Observation) -> CognitiveBinding | None:
        """Gözlemi UCEL ifadesine dönüştür."""
        if obs.type == ObservationType.INDICATOR:
            # RSI < 30 gibi basit bir karşılaştırma oluştur
            rsi = obs.data.get("rsi", 50)
            expr = Expression(
                name=f"obs_{obs.id}",
                description=obs.description,
                root=Comparison(
                    op=OpType.LT,
                    left=Variable(name="RSI"),
                    right=Constant(value=30),
                ),
            )
            return CognitiveBinding(
                source_type="observation",
                source_id=obs.id,
                expression=expr,
                confidence=0.95 if rsi < 30 else 0.5,
            )
        return None

    def observation_to_knowledge(self, binding: CognitiveBinding) -> KnowledgeEntry:
        """CognitiveBinding'i KnowledgeEntry'ye dönüştür."""
        return KnowledgeEntry(
            category=KnowledgeCategory.OBSERVATION,
            conditions={"expression": binding.expression.description},
            result={"evaluated": binding.expression.root.explain()},
            source="cognitive_binder",
        )

    def knowledge_to_belief(self, binding: CognitiveBinding, category: str = "indicator") -> Belief:
        """CognitiveBinding'den Belief oluştur."""
        return Belief(
            direction="LONG" if binding.confidence > 0.6 else "WAIT",
            strength=binding.confidence,
            uncertainty=1.0 - binding.confidence,
            evidence_paths=[binding.expression.description] if binding.expression else [],
            assumptions=[binding.expression.root.explain()] if binding.expression else [],
            total_opinions=binding.evidence_count,
        )

    def belief_to_hypothesis(self, belief: Belief) -> Hypothesis:
        """Belief'ten test edilebilir hipotez üret."""
        return Hypothesis(
            statement=f"Test: direction={belief.direction}, strength={belief.strength}",
            belief_ids=[belief.id],
            sample_size=belief.total_opinions,
            proposed_experiment=f"Verify if {belief.direction} holds in current market",
        )
