"""Cognitive Binder — Observation → Knowledge → Belief → Hypothesis döngüsünü UCEL ile bağlar."""
from contracts.cognitive_binding import CognitiveBinding
from contracts.expression import Expression, Comparison, Variable, Constant, OpType, LogicalAnd
from contracts.observation import Observation, ObservationType
from contracts.knowledge import KnowledgeEntry, KnowledgeCategory
from contracts.belief import Belief
from contracts.hypothesis import Hypothesis

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
            statement=binding.expression.root.explain(),
            expression=binding.expression.description,
            category=category,
            confidence=binding.confidence,
            evidence_count=binding.evidence_count,
        )

    def belief_to_hypothesis(self, belief: Belief) -> Hypothesis:
        """Belief'ten test edilebilir hipotez üret."""
        return Hypothesis(
            statement=f"Test: {belief.statement}",
            belief_ids=[belief.id],
            sample_size=belief.evidence_count,
            proposed_experiment=f"Verify if {belief.expression} holds in current market",
        )
