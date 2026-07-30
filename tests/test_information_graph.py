"""Information Graph V2 testleri."""
from contracts.information_graph import InformationGraph


def test_independence_score_max():
    graph = InformationGraph()
    score = graph.compute_independence([
        "technical_agent", "news_agent", "onchain_agent", "macro_agent"
    ])
    assert score == 1.0

def test_independence_score_low():
    graph = InformationGraph()
    score = graph.compute_independence([
        "technical_agent", "technical_agent", "quant_agent"
    ])
    assert score < 1.0
