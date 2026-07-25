"""Hypothesis Generator — Knowledge + Belief'ten hipotez üretir."""
from contracts.experiment import Experiment
from contracts.knowledge import KnowledgeCategory
from services.belief_service import BeliefService
from services.knowledge_service import KnowledgeService


class HypothesisGenerator:
    def __init__(self, knowledge: KnowledgeService, belief: BeliefService):
        self.knowledge = knowledge
        self.belief = belief

    def analyze_and_generate(self, symbol: str | None = None) -> list[Experiment]:
        """Knowledge'ı tara, pattern bul, hipotez üret."""
        entries = self.knowledge.query(symbol=symbol)

        hypotheses = []

        # Örnek: Volatilite yüksekken başarı düşüyor mu?
        high_vol_trades = [
            e for e in entries
            if e.category == KnowledgeCategory.TRADE_RESULT
            and e.conditions.get("volatility", 0) > 3.0
        ]
        low_vol_trades = [
            e for e in entries
            if e.category == KnowledgeCategory.TRADE_RESULT
            and e.conditions.get("volatility", 0) <= 3.0
        ]

        if len(high_vol_trades) >= 10 and len(low_vol_trades) >= 10:
            high_win_rate = sum(1 for e in high_vol_trades if e.result.get("pnl", 0) > 0) / len(high_vol_trades)
            low_win_rate = sum(1 for e in low_vol_trades if e.result.get("pnl", 0) > 0) / len(low_vol_trades)

            if low_win_rate - high_win_rate > 0.1:
                exp = Experiment(
                    name="Reduce position in high volatility",
                    hypothesis=f"High volatility (>3%) reduces win rate. High vol: {high_win_rate:.0%}, Low vol: {low_win_rate:.0%}. Test: reduce position size by 30% when vol > 3%.",
                    prompt_version="current",
                    feature_version="current",
                )
                hypotheses.append(exp)

        # Zayıflayan belief'leri tara
        weakening = self.belief.list_weakening()
        for belief in weakening:
            exp = Experiment(
                name=f"Re-evaluate: {belief.statement[:60]}",
                hypothesis=f"Belief '{belief.statement}' confidence dropped to {belief.confidence}. Retest with recent data.",
                prompt_version="current",
                feature_version="current",
            )
            hypotheses.append(exp)

        return hypotheses
