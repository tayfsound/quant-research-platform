"""Research Lab testleri — asla trade yapmaz, sadece KB'ye yazar."""
from contracts.hypothesis import HypothesisStatus
from services.research_lab import ResearchLab


class MockBacktester:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, expression: str, data: dict) -> dict:
        self.calls.append((expression, data))
        return self.result


class MockDataProvider:
    def __init__(self, data=None):
        self.data = data or {"samples": 100}
        self.calls = []

    def fetch(self, symbol: str, timeframe: str, limit: int) -> dict:
        self.calls.append((symbol, timeframe, limit))
        return self.data


class MockKnowledgeBase:
    def __init__(self):
        self.entries: list[dict] = []
        self.calls = []

    def add_wisdom(self, category: str, principle: str, source: str, confidence: float):
        self.calls.append((category, principle, source, confidence))
        self.entries.append({
            "category": category,
            "principle": principle,
            "source": source,
            "confidence": confidence,
        })


def test_research_lab_never_trades():
    kb = MockKnowledgeBase()
    backtester = MockBacktester({
        "samples": 120,
        "win_rate": 0.65,
        "total_trades": 120,
        "p_value": 0.01,
        "confidence": 0.85,
    })
    data = MockDataProvider()
    lab = ResearchLab(backtester, data, kb)

    result = lab.run_cycle({
        "symbol": "BTCUSDT",
        "description": "ATH followed by 3 red candles",
        "data": {},
    })

    assert result is not None
    assert result.status == HypothesisStatus.CONFIRMED
    assert len(kb.calls) == 1
    assert "BTCUSDT" in kb.entries[0]["principle"]


def test_generate_hypothesis_ath_red_candles():
    lab = ResearchLab(MockBacktester({}), MockDataProvider(), MockKnowledgeBase())
    hypothesis = lab.generate_hypothesis({
        "symbol": "ETHUSDT",
        "description": "ATH followed by 3 red candles",
        "data": {},
    })
    assert hypothesis is not None
    assert hypothesis.status == HypothesisStatus.PROPOSED
    assert "ATH" in hypothesis.statement


def test_generate_hypothesis_rsi_volume():
    lab = ResearchLab(MockBacktester({}), MockDataProvider(), MockKnowledgeBase())
    hypothesis = lab.generate_hypothesis({
        "symbol": "BTCUSDT",
        "description": "oversold bounce",
        "data": {"rsi": 25, "volume_surge": True},
    })
    assert hypothesis is not None
    assert "RSI" in hypothesis.statement


def test_test_hypothesis_confirmed():
    kb = MockKnowledgeBase()
    backtester = MockBacktester({
        "samples": 80,
        "win_rate": 0.60,
        "total_trades": 80,
        "p_value": 0.03,
        "confidence": 0.80,
    })
    lab = ResearchLab(backtester, MockDataProvider(), kb)
    hypothesis = lab.generate_hypothesis({
        "symbol": "BTCUSDT",
        "description": "ATH followed by 3 red candles",
        "data": {},
    })

    tested = lab.test_hypothesis(hypothesis)
    assert tested.status == HypothesisStatus.CONFIRMED
    assert tested.samples_tested == 80
    assert tested.backtest_result is not None


def test_test_hypothesis_rejected():
    lab = ResearchLab(
        MockBacktester({
            "samples": 100,
            "win_rate": 0.40,
            "total_trades": 100,
            "p_value": 0.15,
            "confidence": 0.30,
        }),
        MockDataProvider(),
        MockKnowledgeBase(),
    )
    hypothesis = lab.generate_hypothesis({
        "symbol": "BTCUSDT",
        "description": "ATH followed by 3 red candles",
        "data": {},
    })
    tested = lab.test_hypothesis(hypothesis)
    assert tested.status == HypothesisStatus.REJECTED


def test_promote_to_knowledge_only_confirmed():
    kb = MockKnowledgeBase()
    lab = ResearchLab(MockBacktester({}), MockDataProvider(), kb)

    confirmed = lab.generate_hypothesis({
        "symbol": "BTCUSDT",
        "description": "ATH followed by 3 red candles",
        "data": {},
    })
    confirmed.status = HypothesisStatus.CONFIRMED
    confirmed.confidence = 0.75

    promoted = lab.promote_to_knowledge(confirmed)
    assert promoted is True
    assert len(kb.entries) == 1


def test_promote_to_knowledge_rejected_not_added():
    kb = MockKnowledgeBase()
    lab = ResearchLab(MockBacktester({}), MockDataProvider(), kb)

    rejected = lab.generate_hypothesis({
        "symbol": "BTCUSDT",
        "description": "ATH followed by 3 red candles",
        "data": {},
    })
    rejected.status = HypothesisStatus.REJECTED

    promoted = lab.promote_to_knowledge(rejected)
    assert promoted is False
    assert len(kb.entries) == 0
