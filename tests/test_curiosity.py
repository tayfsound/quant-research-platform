"""Curiosity Engine testleri."""
from contracts.memory import Episode, EpisodicMemory, SemanticMemory
from services.curiosity_engine import CuriosityEngine
from services.self_evaluator import SelfEvaluator


def test_curiosity_from_errors():
    em = EpisodicMemory()
    sm = SemanticMemory()
    evaluator = SelfEvaluator(em, sm)
    curiosity = CuriosityEngine(em)

    for i in range(20):
        em.add_episode(Episode(
            symbol="BTCUSDT",
            binding_expression="RSI < 30",
            outcome={"pnl": -100},
        ))

    analysis = evaluator.analyze_outcomes(last_n=20)
    adjustments = evaluator.adjust_beliefs(analysis)
    proposals = curiosity.analyze_and_generate(analysis, adjustments)
    assert len(proposals) >= 1

def test_curiosity_top_proposals():
    em = EpisodicMemory()
    curiosity = CuriosityEngine(em)

    # Yeterli episode yoksa boş döner
    top = curiosity.top_proposals(3)
    assert len(top) == 0
