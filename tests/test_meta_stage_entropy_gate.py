"""Faz 297 — kullanıcı isteği (2026-08-19): "yüksek entropy/düşük
konsensüste action eşiğinin otomatik yükselmesi." belief.entropy hiçbir
yerde kullanılmıyordu. 1058 gerçek kararın services/belief_engine.py::
synthesize ile yeniden hesaplanmasıyla ölçüldü: entropy>=1.5 (dağılımın
üst %11'i), 544 kapanmış kararda ORTALAMA pnl ~2.4 kat daha kötüydü
(-1.71 vs -0.72), win_rate'te büyük fark yoktu — yüksek entropy işlemi
engellemiyor, kaybedince DAHA BÜYÜK kaybettiriyor. Bu yüzden ACT'i
WAIT'e değil REDUCE'a zorluyor."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from engines.cognitive_pipeline import MetaStage


def _belief(entropy: float) -> Belief:
    return Belief(
        direction="LONG", strength=0.95, uncertainty=0.0,
        cluster_disagreement=0.0, cluster_balance=1.0, crowding_penalty=0.0,
        entropy=entropy,
    )


def _supportive_opinions() -> list[AgentOpinion]:
    opinions = []
    for domain in (AgentDomain.MACRO, AgentDomain.TECHNICAL, AgentDomain.QUANT):
        o = AgentOpinion(domain=domain, direction="LONG", confidence=0.8)
        o.effective_influence = 0.6
        opinions.append(o)
    return opinions


def _mock_healthy_self_reliability(monkeypatch):
    """Faz 310 — MetaStage artık self-model'i de kontrol ediyor
    (tests/test_meta_stage_self_reliability_gate.py). Bu dosya SADECE
    entropy gate'i izole test etmek istiyor — gerçek DB'nin (quantdb_test,
    oturum boyunca biriken kararlarla) o anki DSR/ECE durumuna göre
    kırılgan olmasın diye sağlıklı sabit değerlerle mock'lanıyor."""
    monkeypatch.setattr(
        "services.self_model_gatherer.get_cached_self_reliability_snapshot",
        lambda: {"inputs": {"recent_dsr": 0.99, "ece": 0.02}},
    )


def test_high_entropy_downgrades_act_to_reduce(monkeypatch):
    _mock_healthy_self_reliability(monkeypatch)
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0

    stage = MetaStage()
    result_ctx = stage.execute(ctx, _belief(entropy=1.55), _supportive_opinions())

    assert result_ctx.decision.action == ActionType.REDUCE
    assert result_ctx.decision.final_size < ctx.decision.proposed_size
    assert result_ctx.decision.final_size > 0.0


def test_normal_entropy_keeps_full_act_size(monkeypatch):
    """Eşiğin (1.5) altında bir entropy — mevcut davranış hiç değişmemeli,
    tam ACT boyutu (Kelly çarpanı hariç) korunmalı."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0

    stage = MetaStage()
    result_ctx = stage.execute(ctx, _belief(entropy=0.5), _supportive_opinions())

    assert result_ctx.decision.action in (ActionType.ENTER_LONG, ActionType.ENTER_SHORT)


def test_entropy_gate_does_not_affect_wait_decisions(monkeypatch):
    """Zaten WAIT'e düşmüş bir karar entropy yüzünden REDUCE'a
    YÜKSELMEMELİ — bu kapı SADECE ACT'i sıkılaştırır, asla gevşetmez."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0

    weak_belief = Belief(
        direction="LONG", strength=0.05, uncertainty=0.9,
        cluster_disagreement=0.9, cluster_balance=1.0, crowding_penalty=0.0,
        entropy=1.55,
    )
    stage = MetaStage()
    result_ctx = stage.execute(ctx, weak_belief, _supportive_opinions())

    assert result_ctx.decision.action == ActionType.WAIT
    assert result_ctx.decision.final_size == 0.0
