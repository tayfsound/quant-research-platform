"""Curiosity Engine — hata analizinden yeni deneyler üretir."""
from contracts.curiosity import CuriositySignal, ExperimentPriority, ExperimentProposal
from contracts.evaluation import BeliefAdjustment, OutcomeAnalysis
from contracts.memory import EpisodicMemory


class CuriosityEngine:
    def __init__(self, episodic: EpisodicMemory):
        self.episodic = episodic
        self.signals: list[CuriositySignal] = []
        self.proposals: list[ExperimentProposal] = []

    def analyze_and_generate(
        self,
        analysis: OutcomeAnalysis,
        adjustments: list[BeliefAdjustment],
    ) -> list[ExperimentProposal]:
        """Hata analizinden merak sinyalleri ve deney önerileri üret."""
        proposals: list[ExperimentProposal] = []

        # 1. En çok hata yapılan koşullardan merak sinyali üret
        for condition in analysis.top_error_conditions[:2]:
            signal = CuriositySignal(
                question=f"Why does condition '{condition}' fail so often?",
                source="error_analysis",
                priority=ExperimentPriority.HIGH,
                information_gain=0.8,
            )
            self.signals.append(signal)
            proposals.append(ExperimentProposal(
                curiosity_id=signal.id,
                hypothesis=f"Condition '{condition}' may need parameter adjustment",
                test_expression=condition,
                estimated_value=0.7,
            ))

        # 2. Zayıflayan belief'lerden merak sinyali
        for adj in adjustments:
            if adj.adjustment_type in ("weaken", "invalidate"):
                signal = CuriositySignal(
                    question=f"Is belief '{adj.belief_expression}' still valid?",
                    source="belief_gap",
                    priority=ExperimentPriority.HIGH if adj.adjustment_type == "invalidate" else ExperimentPriority.MEDIUM,
                    information_gain=0.9,
                )
                self.signals.append(signal)
                proposals.append(ExperimentProposal(
                    curiosity_id=signal.id,
                    hypothesis=f"Retest belief: {adj.belief_expression} with more data",
                    test_expression=adj.belief_expression,
                    estimated_value=0.8,
                ))

        # 3. Keşfedilmemiş alanlar (rastgele sinyal — %20 ihtimal)
        import random
        if random.random() < 0.2 and len(self.episodic.episodes) > 50:
            signal = CuriositySignal(
                question="Explore new feature combinations for untested regimes",
                source="exploration",
                priority=ExperimentPriority.LOW,
                information_gain=0.4,
            )
            self.signals.append(signal)
            proposals.append(ExperimentProposal(
                curiosity_id=signal.id,
                hypothesis="Random exploration of feature space",
                test_expression="random_exploration",
                estimated_value=0.3,
            ))

        self.proposals.extend(proposals)
        return proposals

    def top_proposals(self, n: int = 3) -> list[ExperimentProposal]:
        """En yüksek değerli deney önerilerini döndür."""
        return sorted(self.proposals, key=lambda p: p.estimated_value, reverse=True)[:n]
