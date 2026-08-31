"""Faz 342 — kullanıcı isteği: "short pozisyonlar neden karlı değil?"
Gerçek 1577 kapanmış kararla ölçüldü: council'in SHORT/bearish/low
kombinasyonundaki isabeti SADECE %8.3 (n=424, toplam -$604) — LONG/
bearish/low ise %95.2 (n=398, +$141). "bearish_low" (EMA20<EMA50 + düşük
gerçekleşen volatilite) fiilen bir taban/konsolidasyon kurulumu, düşüş
devamı değil. SADECE bu spesifik kombinasyonda (yön=SHORT + trend=bearish
+ volatilite=low) WAIT'e zorlanıyor."""
import pytest

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
    # Faz 370-devam — kritik bulgu: is_direction_paused (regime_reversal_
    # guardian.py) burada mock'lanmıyordu ve GERÇEK quantdb_test.decisions
    # tablosunu sorguluyordu — tam pytest suite'i çalıştırıldığında AYNI
    # oturumdaki BAŞKA testlerin bıraktığı ardışık SHORT kayıpları bu
    # testleri (bearish_low harici SHORT senaryolarını "WAIT'e
    # zorlanmamalı" diye bekleyenleri) yanlışlıkla kırıyordu — testler
    # TEK BAŞINA her zaman geçiyordu (izole çalıştırıldığında), sadece
    # sırada başka testlerin ürettiği paylaşılan durumla çakışıyordu. Bu
    # dosyanın kapsamı SADECE bearish_low+SHORT gate'i — ilgisiz bir
    # paylaşılan mekanizmaya bağımlı olmamalı.
    monkeypatch.setattr(
        "services.regime_reversal_guardian.is_direction_paused",
        lambda direction: False,
    )


def _ctx(trend: str | None, volatility_regime: str | None) -> CognitiveCycleContext:
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "live"
    ctx.decision.proposed_size = 1.0
    ctx.market.features = {}
    if trend is not None:
        ctx.market.features["trend"] = trend
    if volatility_regime is not None:
        ctx.market.features["volatility_regime"] = volatility_regime
    return ctx


def test_short_in_bearish_low_forces_wait(monkeypatch):
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(trend="bearish", volatility_regime="low")
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _belief("SHORT"), _supportive_opinions("SHORT"))

    assert result_ctx.decision.action == ActionType.WAIT
    assert result_ctx.decision.final_size == 0.0


def test_long_in_bearish_low_does_not_force_wait(monkeypatch):
    """Gate SADECE SHORT'u hedefliyor — aynı rejimde LONG %95.2 isabetli,
    dokunulmamalı."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(trend="bearish", volatility_regime="low")
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _belief("LONG"), _supportive_opinions("LONG"))

    assert result_ctx.decision.action != ActionType.WAIT


def test_short_in_bearish_normal_does_not_force_wait(monkeypatch):
    """Gate SADECE düşük volatilite alt-rejiminde tetiklenmeli — bearish_
    normal'de SHORT %46.8 isabetli (n=47), bearish_low'un (%8.3) çok
    üzerinde, ayrı bir durum."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(trend="bearish", volatility_regime="normal")
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _belief("SHORT"), _supportive_opinions("SHORT"))

    assert result_ctx.decision.action != ActionType.WAIT


def test_short_in_bullish_low_does_not_force_wait(monkeypatch):
    """Gate SADECE trend=bearish'te tetiklenmeli — bullish_low'da SHORT
    zaten çok nadir/ayrı bir durum, bu gate'in kapsamı dışında."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(trend="bullish", volatility_regime="low")
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _belief("SHORT"), _supportive_opinions("SHORT"))

    assert result_ctx.decision.action != ActionType.WAIT


def test_test_mode_downgrades_wait_to_reduce_scaled_by_confidence(monkeypatch):
    """Faz 388 — kullanıcı bulgusu/isteği (2026-08-31): canlıda 2.5+ saat,
    test modunda da uzun süre hiç pozisyon açılmadı — "güven seviyesi
    kararın verilip verilmeyeceğini değil, boyutunu etkilemeli... işlem
    alsın bütün rejimlerden alsın ki data toplayalım." trading_mode="test"
    iken, bu dosyanın gate'i (short_in_bearish_low) gibi bir WAIT-zorlayan
    gate tetiklense bile, gerçek bir yönlü sinyal (belief.direction) varsa
    REDUCE'a düşülüyor — final_size, REDUCE'un KENDİ formülüyle (proposed_
    size * confidence) orantılı küçülüyor, sıfırlanmıyor."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(trend="bearish", volatility_regime="low")
    ctx.risk.trading_mode = "test"
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _belief("SHORT"), _supportive_opinions("SHORT"))

    assert result_ctx.decision.action == ActionType.REDUCE
    assert result_ctx.decision.final_size > 0.0
    assert result_ctx.decision.final_size == pytest.approx(
        result_ctx.decision.proposed_size * result_ctx.decision.confidence
    )
    override_entries = [
        item["data"] for item in ctx.cognition.relevant_knowledge
        if item.get("type") == "test_mode_wait_override"
    ]
    assert len(override_entries) == 1


def test_live_mode_still_forces_wait_unaffected_by_test_mode_override(monkeypatch):
    """Faz 388 regresyon: canlı modda hiçbir şey değişmemeli — bu dosyanın
    ana testiyle (test_short_in_bearish_low_forces_wait) AYNI senaryo,
    sadece override'ın SADECE test modunda devreye girdiğini bir kez daha
    açıkça kilitliyor."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(trend="bearish", volatility_regime="low")
    assert ctx.risk.trading_mode == "live"
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _belief("SHORT"), _supportive_opinions("SHORT"))

    assert result_ctx.decision.action == ActionType.WAIT
    assert result_ctx.decision.final_size == 0.0


def test_missing_features_do_not_force_wait(monkeypatch):
    """trend/volatility_regime hiç yoksa (ör. yetersiz bar geçmişi)
    fail-closed — gate icat edilmiş bir değerle tetiklenmez."""
    _mock_healthy_self_reliability(monkeypatch)
    ctx = _ctx(trend=None, volatility_regime=None)
    stage = MetaStage()
    result_ctx = stage.execute(ctx, _belief("SHORT"), _supportive_opinions("SHORT"))

    assert result_ctx.decision.action != ActionType.WAIT
