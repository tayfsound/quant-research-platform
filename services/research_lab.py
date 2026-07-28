"""Research Lab — asenkron, trade-bağımsız hipotez üretim ve doğrulama birimi."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from contracts.hypothesis import Hypothesis, HypothesisStatus


class Backtester(Protocol):
    def run(self, expression: str, data: dict) -> dict: ...


class DataProvider(Protocol):
    def fetch(self, symbol: str, timeframe: str, limit: int) -> dict: ...


class KnowledgeBaseWriter(Protocol):
    def add_wisdom(self, category: str, principle: str, source: str, confidence: float): ...


class ResearchLab:
    """Sadece KnowledgeBase'e yazar. Asla trade yapmaz."""

    def __init__(
        self,
        backtester: Backtester,
        data_provider: DataProvider,
        knowledge_base: KnowledgeBaseWriter,
    ):
        self.backtester = backtester
        self.data = data_provider
        self.kb = knowledge_base
        self.hypotheses: list[Hypothesis] = []

    def generate_hypothesis(self, observation: dict) -> Hypothesis | None:
        symbol = observation.get("symbol", "")
        description = observation.get("description", "").lower()
        data = observation.get("data", {})

        if not symbol or not description:
            return None

        if "ath" in description and ("red candle" in description or "red" in description):
            return Hypothesis(
                id=uuid4(),
                statement=f"{symbol}: ATH followed by consecutive red candles → short opportunity",
                test_expression=f"ATH_REDS -> SHORT on {symbol}",
                required_data={"symbol": symbol, "pattern": "ATH_RED_CANDLES", "lookback": 5},
                status=HypothesisStatus.PROPOSED,
                confidence=0.5,
            )

        if data.get("rsi", 50) < 30 and data.get("volume_surge", False):
            return Hypothesis(
                id=uuid4(),
                statement=f"{symbol}: RSI oversold with volume surge → mean-reversion long",
                test_expression=f"RSI<30 AND VOLUME_SURGE -> LONG on {symbol}",
                required_data={"symbol": symbol, "indicators": ["rsi", "volume"], "thresholds": {"rsi": 30}},
                status=HypothesisStatus.PROPOSED,
                confidence=0.5,
            )

        if "breakout" in description and data.get("volume_confirmation", False):
            return Hypothesis(
                id=uuid4(),
                statement=f"{symbol}: Confirmed breakout → momentum continuation",
                test_expression=f"BREAKOUT AND VOLUME_CONFIRM -> MOMENTUM on {symbol}",
                required_data={"symbol": symbol, "pattern": "BREAKOUT", "confirm": "volume"},
                status=HypothesisStatus.PROPOSED,
                confidence=0.5,
            )

        return None

    def test_hypothesis(self, hypothesis: Hypothesis) -> Hypothesis:
        hypothesis.status = HypothesisStatus.TESTING

        required = hypothesis.required_data or {}
        symbol = required.get("symbol", "")
        data = self.data.fetch(symbol=symbol, timeframe="1d", limit=252) if symbol else {"samples": 0}

        result = self.backtester.run(
            expression=hypothesis.test_expression,
            data=data,
        )

        hypothesis.backtest_result = result
        hypothesis.samples_tested = result.get("samples", 0)
        hypothesis.p_value = result.get("p_value")
        hypothesis.confidence = result.get("confidence", 0.0)

        win_rate = result.get("win_rate", 0.0)
        total_trades = result.get("total_trades", 0)
        p_value = result.get("p_value", 1.0)

        if total_trades < 10 or p_value is None:
            hypothesis.status = HypothesisStatus.INCONCLUSIVE
        elif win_rate > 0.55 and p_value < 0.05:
            hypothesis.status = HypothesisStatus.CONFIRMED
        elif p_value >= 0.1 or win_rate < 0.45:
            hypothesis.status = HypothesisStatus.REJECTED
        else:
            hypothesis.status = HypothesisStatus.INCONCLUSIVE

        return hypothesis

    def promote_to_knowledge(self, hypothesis: Hypothesis) -> bool:
        if hypothesis.status != HypothesisStatus.CONFIRMED:
            return False
        if hypothesis.confidence < 0.7:
            return False

        self.kb.add_wisdom(
            category="research_lab",
            principle=hypothesis.statement,
            source=f"research_lab:{hypothesis.id}",
            confidence=hypothesis.confidence,
        )
        return True

    def run_cycle(self, observation: dict) -> Hypothesis | None:
        hypothesis = self.generate_hypothesis(observation)
        if hypothesis is None:
            return None

        self.hypotheses.append(hypothesis)
        tested = self.test_hypothesis(hypothesis)
        self.promote_to_knowledge(tested)
        return tested
