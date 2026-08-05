"""Time Agent testleri — dürüstlük ilkesi: yön tahmini yapmaz, sadece risk işaretler."""
from agents.time_agent import TimeAgent
from contracts.time_context import TimeContext


def test_always_waits_regardless_of_input():
    agent = TimeAgent()
    for ctx in (
        TimeContext(session="asia", day_of_week="Monday"),
        TimeContext(session="us", day_of_week="Friday", is_weekend=True),
        TimeContext(hours_to_funding=0.1),
    ):
        assert agent.analyze(ctx).direction == "WAIT"


def test_funding_settlement_soon_raises_caveat_and_confidence():
    agent = TimeAgent()
    far = agent.analyze(TimeContext(hours_to_funding=6.0))
    near = agent.analyze(TimeContext(hours_to_funding=0.1))
    assert near.confidence > far.confidence
    assert any("funding" in c.lower() for c in near.caveats)


def test_weekend_raises_caveat():
    agent = TimeAgent()
    opinion = agent.analyze(TimeContext(is_weekend=True, hours_to_funding=6.0))
    assert any("weekend" in c.lower() for c in opinion.caveats)
