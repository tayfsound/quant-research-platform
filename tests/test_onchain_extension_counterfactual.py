"""analytics/onchain_extension_counterfactual.py — backlog #51."""
from analytics.onchain_extension_counterfactual import resynthesize_with_onchain_btc_extension
from contracts.agent import AgentDomain, AgentOpinion


def _opinion_dict(domain: AgentDomain, direction: str, confidence: float = 0.8, feature_contributions=None) -> dict:
    o = AgentOpinion(domain=domain, direction=direction, confidence=confidence, feature_contributions=feature_contributions or {})
    o.recalculate()
    return o.model_dump(mode="json")


def test_none_when_onchain_never_voted():
    contributions = [_opinion_dict(AgentDomain.TECHNICAL, "LONG")]
    assert resynthesize_with_onchain_btc_extension(contributions, 0.5, -0.5) is None


def test_none_when_already_btc_scored():
    """network_activity_trend zaten feature_contributions'taysa bu
    zaten BTC (is_btc=True) demektir — karşı-olgusal anlamsız."""
    contributions = [
        _opinion_dict(AgentDomain.ONCHAIN, "LONG", feature_contributions={"network_activity_trend": 0.5}),
        _opinion_dict(AgentDomain.TECHNICAL, "SHORT"),
    ]
    assert resynthesize_with_onchain_btc_extension(contributions, 0.5, 0.0) is None


def test_none_when_btc_state_is_also_neutral():
    contributions = [
        _opinion_dict(AgentDomain.ONCHAIN, "WAIT", confidence=0.0),
        _opinion_dict(AgentDomain.TECHNICAL, "SHORT"),
    ]
    assert resynthesize_with_onchain_btc_extension(contributions, 0.0, 0.0) is None


def test_extension_can_flip_onchain_direction_and_final_belief():
    # technical LONG, macro LONG, onchain (şu an WAIT, score=0) — BTC
    # ağı rising+rising verirse (score=1.0 > 0.4) onchain LONG'a döner.
    contributions = [
        _opinion_dict(AgentDomain.ONCHAIN, "WAIT", confidence=0.0),
        _opinion_dict(AgentDomain.TECHNICAL, "SHORT", confidence=0.9),
        _opinion_dict(AgentDomain.MACRO, "SHORT", confidence=0.9),
    ]
    result = resynthesize_with_onchain_btc_extension(contributions, 0.5, 0.5)
    assert result is not None
    belief, adjusted = result
    onchain_adjusted = next(o for o in adjusted if o.domain == AgentDomain.ONCHAIN)
    assert onchain_adjusted.direction == "LONG"
    assert onchain_adjusted.feature_contributions["network_activity_trend"] == 0.5
    assert onchain_adjusted.feature_contributions["hash_rate_trend"] == 0.5
