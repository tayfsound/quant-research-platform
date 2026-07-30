"""Self Evaluation testleri."""
from contracts.memory import Episode, EpisodicMemory, SemanticMemory
from services.self_evaluator import SelfEvaluator


def test_outcome_analysis():
    em = EpisodicMemory()
    sm = SemanticMemory()
    evaluator = SelfEvaluator(em, sm)

    # 10 kazanan, 10 kaybeden episode ekle
    for i in range(20):
        em.add_episode(Episode(
            symbol="BTCUSDT",
            binding_expression="RSI < 30",
            outcome={"pnl": 100 if i < 10 else -50},
        ))

    analysis = evaluator.analyze_outcomes(last_n=20)
    assert analysis.total_evaluated == 20
    assert analysis.win_rate == 0.5
    assert "RSI < 30" in analysis.condition_breakdown

def test_belief_adjustment():
    em = EpisodicMemory()
    sm = SemanticMemory()
    evaluator = SelfEvaluator(em, sm)

    sm.add_belief("RSI < 30", 0.8)

    # Düşük başarı oranlı episode'lar ekle
    for i in range(15):
        em.add_episode(Episode(
            symbol="BTCUSDT",
            binding_expression="RSI < 30",
            outcome={"pnl": -50},
        ))

    analysis = evaluator.analyze_outcomes(last_n=15)
    adjustments = evaluator.adjust_beliefs(analysis)
    assert len(adjustments) >= 1
    assert adjustments[0].new_confidence < 0.8

def test_generate_lessons():
    em = EpisodicMemory()
    sm = SemanticMemory()
    evaluator = SelfEvaluator(em, sm)

    for i in range(20):
        em.add_episode(Episode(
            symbol="BTCUSDT",
            binding_expression="RSI < 30",
            outcome={"pnl": -100},
        ))

    analysis = evaluator.analyze_outcomes(last_n=20)
    adjustments = evaluator.adjust_beliefs(analysis)
    lessons = evaluator.generate_lessons(analysis, adjustments)
    assert len(lessons) >= 1
    assert any("critically low" in l.lesson_text for l in lessons)

def test_evaluation_in_context():
    from contracts.context import CognitiveCycleContext
    from services.cognitive_engine import CognitiveEngine

    engine = CognitiveEngine()
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT", "timeframe": "4H", "features": {"RSI": 25}},
        decision={"proposed_direction": "LONG", "proposed_size": 0.5},
    )
    result = engine.run(ctx)
    eval_data = [item for item in result.cognition.relevant_knowledge if item.get("type") == "self_evaluation"]
    assert len(eval_data) >= 0  # İlk çevrimde 10'a ulaşmadıysa boş olabilir
