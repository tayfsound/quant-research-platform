"""Agent quality finding: CouncilOrchestrator.deliberate() used to call
`self.debate.run_debate(opinions, {})` with a hardcoded empty context —
RiskChallenger.challenge()'s two most important checks read
`context.get("volatility", 0.0)` / `context.get("crowding_risk", 0.0)`,
both of which could therefore never be anything but 0.0, so they could
never cross their 0.7/0.6 thresholds. The third check (data_quality < 0.5)
was also dead in practice since all four real agents hardcode
data_quality >= 0.75. The risk-challenge layer was effectively inert.

This proves the fix: a real, high-volatility, unanimous (crowded), high-
confidence scenario now actually produces a RiskChallenge."""
from contracts.agent import AgentDomain
from contracts.macro import MacroContext
from contracts.onchain import OnChainContext
from contracts.sentiment import SentimentContext
from contracts.technical import TechnicalContext
from services.council_orchestrator import CouncilOrchestrator
from agents.registry import AgentRegistry


def test_build_debate_context_reflects_real_volatility_and_crowding():
    orchestrator = CouncilOrchestrator(AgentRegistry.create_default())

    from contracts.agent import AgentOpinion

    opinions = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG", confidence=0.9),
        AgentOpinion(domain=AgentDomain.MACRO, direction="LONG", confidence=0.9),
        AgentOpinion(domain=AgentDomain.ONCHAIN, direction="LONG", confidence=0.9),
    ]
    ctx = orchestrator._build_debate_context(
        {AgentDomain.TECHNICAL: TechnicalContext(volatility_regime="high")},
        opinions,
    )
    assert ctx["volatility"] == 0.8
    assert ctx["crowding_risk"] == 1.0


def test_crowded_high_volatility_high_confidence_council_actually_gets_challenged():
    registry = AgentRegistry.create_default()
    orchestrator = CouncilOrchestrator(registry)

    belief, opinions = orchestrator.deliberate({
        AgentDomain.TECHNICAL: TechnicalContext(
            trend="bullish", momentum="strengthening", market_structure="higher_highs",
            ema_alignment="bullish_aligned", volume_confirmation=True, volatility_regime="high",
        ),
        AgentDomain.MACRO: MacroContext(inflation_trend="falling", central_bank_bias="dovish"),
        AgentDomain.ONCHAIN: OnChainContext(exchange_outflow_24h=500_000_000, whale_accumulation=True),
        AgentDomain.SENTIMENT: SentimentContext(fear_greed_index=10.0),
    })

    result = orchestrator.last_debate_result
    assert result is not None
    all_challenges = [c for r in result.rounds for c in r.challenges]
    # Before the fix, this was always empty for ANY input — context was
    # always {}, so volatility/crowding checks could never fire.
    assert len(all_challenges) >= 1
    assert any("volatility" in c.reason.lower() or "crowding" in c.reason.lower() for c in all_challenges)
