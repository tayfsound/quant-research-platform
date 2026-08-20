"""Faz 328 — Opportunity Quality (Grup B) canlıya bağlandı. Gerçek
veriyle ölçüldü (services/opportunity_quality_gatherer.py, 1410 gerçek
kapanmış işlem): council'in 9 ajan oyu arasındaki anlaşma "low"
kovasındayken kazanma oranı %64.0 (n=1033), "medium" kovasındayken %93.0
(n=370) — SADECE "low" kova indirilir, "high" (n=7, yetersiz) ve
"medium" hiç değişmez."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from services.decision_fusion import DecisionFusion


def _ctx(confidence=0.6):
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "BTCUSDT"
    ctx.market.raw_snapshot = {"close": 100.0}
    ctx.decision.proposed_direction = "LONG"
    ctx.decision.proposed_size = 0.3
    ctx.decision.final_size = 0.3
    ctx.decision.confidence = confidence
    ctx.decision.action = ActionType.ENTER_LONG
    # stop_loss=5/take_profit=6 -> ham confidence (0.6) ile EV pozitif
    # (0.6*6 - 0.4*5 = 1.6 > 0, ENTER). "low" anlaşma indirimi confidence'ı
    # 0.6*0.6883≈0.413'e düşürür -> EV negatife döner (WAIT) — indirimin
    # GERÇEK karar üzerindeki etkisini (sadece bir iç değişkeni değil)
    # doğrulamak için kasıtlı seçildi.
    ctx.decision.stop_loss_distance = 5.0
    ctx.decision.take_profit_distance = 6.0
    return ctx


def _belief():
    return Belief(direction="LONG", strength=0.6)


def _opinion(domain: AgentDomain, direction: str) -> AgentOpinion:
    return AgentOpinion(agent_id=f"{domain.value}_v1", domain=domain, direction=direction, confidence=0.6)


# 9 ajan, hepsi LONG -> tam anlaşma (agreement=1.0, "high" kovası ama
# gerçek/canlı senaryoda alakasız — burada sadece agreement=1.0 üretmek
# için).
_UNANIMOUS_OPINIONS = [
    _opinion(d, "LONG") for d in (
        AgentDomain.TECHNICAL, AgentDomain.MACRO, AgentDomain.ONCHAIN, AgentDomain.NEWS,
        AgentDomain.PSYCHOLOGY, AgentDomain.QUANT, AgentDomain.RISK, AgentDomain.BEHAVIORAL,
        AgentDomain.ORDER_FLOW,
    )
]

# 9 ajan, 3-3-3 LONG/SHORT/WAIT bölünmüş -> maksimum bölünmüşlük
# (agreement=0.0, "low" kovası).
_SPLIT_OPINIONS = (
    [_opinion(d, "LONG") for d in (AgentDomain.TECHNICAL, AgentDomain.MACRO, AgentDomain.ONCHAIN)]
    + [_opinion(d, "SHORT") for d in (AgentDomain.NEWS, AgentDomain.PSYCHOLOGY, AgentDomain.QUANT)]
    + [_opinion(d, "WAIT") for d in (AgentDomain.RISK, AgentDomain.BEHAVIORAL, AgentDomain.ORDER_FLOW)]
)


def test_low_agreement_discounts_confidence(monkeypatch):
    monkeypatch.setattr("services.decision_fusion.calibrate_confidence", lambda c, curve=None: c)

    ctx = DecisionFusion().evaluate(_ctx(confidence=0.6), _belief(), opinions=_SPLIT_OPINIONS)

    assert abs(ctx.decision.confidence - (0.6 * 0.6883)) < 1e-3  # ctx.decision.confidence round(x, 4)
    assert any(
        k.get("type") == "opportunity_quality" for k in ctx.cognition.relevant_knowledge
    )


def test_high_agreement_does_not_change_confidence(monkeypatch):
    monkeypatch.setattr("services.decision_fusion.calibrate_confidence", lambda c, curve=None: c)

    ctx = DecisionFusion().evaluate(_ctx(confidence=0.6), _belief(), opinions=_UNANIMOUS_OPINIONS)

    assert abs(ctx.decision.confidence - 0.6) < 1e-9
    assert not any(
        k.get("type") == "opportunity_quality" for k in ctx.cognition.relevant_knowledge
    )


def test_no_opinions_leaves_confidence_unchanged(monkeypatch):
    """opinions verilmezse (ör. eski/izole çağrı) davranış hiç
    değişmemeli — fail-closed."""
    monkeypatch.setattr("services.decision_fusion.calibrate_confidence", lambda c, curve=None: c)

    ctx = DecisionFusion().evaluate(_ctx(confidence=0.6), _belief())

    assert abs(ctx.decision.confidence - 0.6) < 1e-9
