"""Faz 194: "Nasdaq/S&P500 ile korele gidiyor" — ikisi de aynı yönde gerçek
trend gösterdiğinde kripto analizine ikinci görüş olarak akıyor."""
from uuid import uuid4

from agents.technical_agent import TechnicalAgent
from contracts.context import CognitiveCycleContext
from contracts.decision_event import DecisionEvent
from contracts.technical import TechnicalContext
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.context_adapter import ContextAdapter


def _persist_index_decision(symbol: str, trend: str):
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(DecisionEvent(
            id=uuid4(),
            symbol=symbol,
            proposed_direction="WAIT",
            market_snapshot={"features": {"trend": trend}, "raw_snapshot": {}},
        ))


def test_correlated_market_trend_is_bullish_when_both_indices_agree():
    _persist_index_decision("^IXIC", "bullish")
    _persist_index_decision("^GSPC", "bullish")

    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT"})
    result = ContextAdapter().to_technical(ctx)

    assert result.correlated_market_trend == "bullish"


def test_correlated_market_trend_is_none_when_indices_disagree():
    _persist_index_decision("^IXIC", "bullish")
    _persist_index_decision("^GSPC", "bearish")

    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT"})
    result = ContextAdapter().to_technical(ctx)

    assert result.correlated_market_trend is None


def test_correlated_market_trend_is_none_for_non_crypto_symbols():
    _persist_index_decision("^IXIC", "bullish")
    _persist_index_decision("^GSPC", "bullish")

    ctx = CognitiveCycleContext(market={"symbol": "AAPL"})
    result = ContextAdapter().to_technical(ctx)

    assert result.correlated_market_trend is None


def test_technical_agent_adds_evidence_when_correlation_confirms():
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        correlated_market_trend="bullish",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"
    assert any("Nasdaq" in e for e in opinion.evidence)


def test_technical_agent_adds_caveat_when_correlation_conflicts():
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        correlated_market_trend="bearish",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"  # kendi iç görüşü hâlâ geçerli, ezilmiyor
    assert any("çelişiyor" in c for c in opinion.caveats)
