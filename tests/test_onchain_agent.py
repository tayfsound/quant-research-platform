"""OnChain Agent testleri."""
from agents.onchain_agent import OnChainAgent
from contracts.onchain import OnChainContext

def test_whale_accumulation_generates_long():
    agent = OnChainAgent()
    ctx = OnChainContext(
        exchange_outflow_24h=500_000_000,
        exchange_inflow_24h=100_000_000,
        whale_accumulation=True,
        stablecoin_mint_24h=200_000_000,
    )
    opinion = agent.analyze(ctx)
    assert opinion.domain.value == "onchain"
    assert opinion.direction == "LONG"
    assert opinion.confidence > 0

def test_whale_distribution_generates_short():
    agent = OnChainAgent()
    ctx = OnChainContext(
        exchange_inflow_24h=500_000_000,
        exchange_outflow_24h=100_000_000,
        whale_distribution=True,
        mvrv_zscore=3.5,
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "SHORT"
    assert opinion.confidence > 0

def test_mvrv_extremes():
    agent = OnChainAgent()
    ctx_low = OnChainContext(mvrv_zscore=-1.5)
    ctx_high = OnChainContext(mvrv_zscore=4.0)

    opinion_low = agent.analyze(ctx_low)
    opinion_high = agent.analyze(ctx_high)

    assert opinion_low.direction == "LONG"
    assert opinion_high.direction == "SHORT"

def test_conflicting_whale_signal_waits():
    agent = OnChainAgent()
    ctx = OnChainContext(
        whale_accumulation=True,
        whale_distribution=True,
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "WAIT"
    assert len(opinion.caveats) > 0
    assert any("Conflicting" in c for c in opinion.caveats)
