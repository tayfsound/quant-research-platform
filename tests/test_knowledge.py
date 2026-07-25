"""Knowledge sistemi testleri."""
from contracts.knowledge import KnowledgeEntry
from services.knowledge_service import KnowledgeService


def test_record_and_query():
    svc = KnowledgeService()
    entry = KnowledgeEntry(
        category="trade_result",
        symbol="BTCUSDT",
        timeframe="4H",
        conditions={"rsi": "<30"},
        result={"win_rate": 0.72, "n": 184, "confidence": 0.83},
    )
    svc.record(entry)
    results = svc.query(symbol="BTCUSDT")
    assert len(results) == 1
    assert results[0].result["win_rate"] == 0.72

def test_statistics():
    svc = KnowledgeService()
    svc.record(KnowledgeEntry(category="trade_result", symbol="BTC", result={"pnl": 100, "confidence": 0.8}))
    svc.record(KnowledgeEntry(category="trade_result", symbol="BTC", result={"pnl": -50, "confidence": 0.6}))
    stats = svc.get_statistics(symbol="BTC")
    assert stats["total_trades"] == 2
    assert stats["win_rate"] == 0.5
