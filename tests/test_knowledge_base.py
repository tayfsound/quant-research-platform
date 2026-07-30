"""Knowledge Base testleri — InformationGraph tabanlı bilgi deposu."""
from services.knowledge_base import KnowledgeBase


def test_add_wisdom():
    kb = KnowledgeBase()
    entry = kb.add_wisdom(
        category="risk_management",
        principle="Test principle",
        source="test",
        confidence=0.9,
    )
    assert entry.category == "risk_management"
    assert entry.principle == "Test principle"
    assert entry.confidence == 0.9
    assert len(kb.wisdom_entries) == 5  # 4 seeded + 1 added


def test_query_relevant_drawdown():
    kb = KnowledgeBase()
    results = kb.query_relevant(
        market_context={
            "symbol": "BTCUSDT",
            "features": {"drawdown": 0.25},
        },
        decision_context={},
    )
    assert len(results) > 0
    risk_entries = [r for r in results if r["category"] == "risk_management"]
    assert len(risk_entries) >= 1


def test_query_relevant_correlated_signals():
    kb = KnowledgeBase()
    results = kb.query_relevant(
        market_context={
            "symbol": "ETHUSDT",
            "features": {"correlation": 0.8, "num_signals": 3},
        },
        decision_context={},
    )
    signal_entries = [r for r in results if r["category"] == "signal_processing"]
    assert len(signal_entries) >= 1


def test_validate_lesson_profitable():
    kb = KnowledgeBase()
    entry = kb.add_wisdom(
        category="expected_value",
        principle="EV check",
        source="test",
        confidence=0.8,
    )
    is_valid = kb.validate_lesson(str(entry.id), {"pnl": 100.0})
    assert is_valid is True
    assert entry.validation_count == 1


def test_validate_lesson_invalidated_after_losses():
    kb = KnowledgeBase()
    entry = kb.add_wisdom(
        category="expected_value",
        principle="EV check",
        source="test",
        confidence=0.8,
    )
    for _ in range(3):
        kb.validate_lesson(str(entry.id), {"pnl": -10.0})
    assert entry.invalidated is True
