"""Faz 352 — Regime Reversal Guardian'ın MetaStage gate'i. Kullanıcı
fikri, GERÇEK bir olayla doğrulandı: LONG'da art arda 14 stop-loss, aynı
anda 275 açık LONG'un 170'i zararda. Faz 342'nin bearish_low SHORT
gate'iyle AYNI desen — belief.direction'da streak eşiği aşılmışsa WAIT'e
zorlanır, diğer yön/durumlar etkilenmez."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from engines.cognitive_pipeline import MetaStage


def _belief(direction: str) -> Belief:
    return Belief(
        direction=direction, strength=0.95, uncertainty=0.0,
        cluster_disagreement=0.0, cluster_balance=1.0, crowding_penalty=0.0,
    )


def _supportive_opinions(direction: str) -> list[AgentOpinion]:
    opinions = []
    for domain in (AgentDomain.MACRO, AgentDomain.TECHNICAL, AgentDomain.QUANT):
        o = AgentOpinion(domain=domain, direction=direction, confidence=0.8)
        o.effective_influence = 0.6
        opinions.append(o)
    return opinions


def _mock_healthy_self_reliability(monkeypatch):
    monkeypatch.setattr(
        "services.self_model_gatherer.get_cached_self_reliability_snapshot",
        lambda: {"inputs": {"recent_dsr": 0.99, "ece": 0.02}},
    )


def _ctx() -> CognitiveCycleContext:
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0
    ctx.market.features = {}
    return ctx


def test_direction_paused_forces_wait(monkeypatch):
    _mock_healthy_self_reliability(monkeypatch)
    monkeypatch.setattr(
        "services.regime_reversal_guardian.is_direction_paused",
        lambda direction: direction == "LONG",
    )
    stage = MetaStage()
    result_ctx = stage.execute(_ctx(), _belief("LONG"), _supportive_opinions("LONG"))

    assert result_ctx.decision.action == ActionType.WAIT
    assert result_ctx.decision.final_size == 0.0


def test_other_direction_not_paused_is_unaffected(monkeypatch):
    """LONG duraklatılmışken SHORT'a hiç dokunulmamalı — yön-bazlı,
    global değil."""
    _mock_healthy_self_reliability(monkeypatch)
    monkeypatch.setattr(
        "services.regime_reversal_guardian.is_direction_paused",
        lambda direction: direction == "LONG",
    )
    stage = MetaStage()
    result_ctx = stage.execute(_ctx(), _belief("SHORT"), _supportive_opinions("SHORT"))

    assert result_ctx.decision.action != ActionType.WAIT


def test_no_direction_paused_does_not_force_wait(monkeypatch):
    _mock_healthy_self_reliability(monkeypatch)
    monkeypatch.setattr("services.regime_reversal_guardian.is_direction_paused", lambda direction: False)
    stage = MetaStage()
    result_ctx = stage.execute(_ctx(), _belief("LONG"), _supportive_opinions("LONG"))

    assert result_ctx.decision.action != ActionType.WAIT


def test_guardian_check_failure_fails_open_and_does_not_force_wait(monkeypatch):
    """Fail-closed felsefesi burada TERSİNE işliyor: guardian'ın kendisi
    hata verirse, YENİ bir kısıtlama uygulanmaz (mevcut davranış korunur)
    — bkz. engines/cognitive_pipeline.py'deki dış try/except."""
    _mock_healthy_self_reliability(monkeypatch)

    def _raise(direction):
        raise RuntimeError("boom")

    monkeypatch.setattr("services.regime_reversal_guardian.is_direction_paused", _raise)
    stage = MetaStage()
    result_ctx = stage.execute(_ctx(), _belief("LONG"), _supportive_opinions("LONG"))

    assert result_ctx.decision.action != ActionType.WAIT
