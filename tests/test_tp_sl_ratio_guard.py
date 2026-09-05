"""Faz 413 (2026-09-06) — kullanıcı bulgusu (JPMUSDT: "hedefe ulaştı"
diyordu, pnl $0,49): MAX_ADAPTIVE_BARRIER_RATIO SADECE Adaptive Barrier
tablosundan gelen çifti kontrol ediyordu — confluence-snap + min_target_pct
tabanı bundan SONRA, stop'a hiç bakmadan hedefi bağımsız sıkıştırabiliyordu.
Gerçek ölçüm: Faz 406 sonrası açılan 619 pozisyonun %68'i (423) stop:hedef
oranı 5.5'i aşıyordu (medyan 9:1, en kötüsü 22.3:1). Bu testler hem
RiskTargetStage'in son-çare genişletmesini hem Faz 409'un AYNI görünürlük
deseninin (RecordingStage/DecisionRecorder) tekrarlandığını doğruluyor."""
from contracts.context import CognitiveCycleContext
from services.decision_recorder import DecisionRecorder


def _base_ctx(**overrides):
    market = {
        "symbol": "TESTUSDT",
        "raw_snapshot": {"close": 100.0},
        "features": {"daily_atr_pct": 0.02},
    }
    market.update(overrides.pop("market", {}))
    ctx = CognitiveCycleContext(
        market=market,
        decision={"proposed_direction": "SHORT", "final_size": 1.0},
        **overrides,
    )
    return ctx


def test_disproportionately_small_target_is_widened_to_respect_the_ratio():
    from engines.cognitive_pipeline import RiskTargetStage

    ctx = _base_ctx()
    # SHORT: stop_mult=2.5, target_mult=1.8 (varsayılan) -> stop_pct=0.05,
    # target_pct=0.036 -- oran ~1.39, guard'ı tetiklemez. Confluence
    # simüle etmek için relevant_knowledge'a doğrudan sıkıştırılmış bir
    # hedef bırakmak yerine, gerçek üretim yolunu (confluence_zones) fiyata
    # ÇOK yakın bir bölge vererek tetikliyoruz.
    ctx.market.features["confluence_zones"] = [
        {"level": 99.6, "method_count": 2, "methods": ["pivot", "volume_profile"]},
    ]
    stage = RiskTargetStage()
    result = stage.execute(ctx)

    stop_pct = result.decision.stop_loss_distance / 100.0
    target_pct = result.decision.take_profit_distance / 100.0
    assert stop_pct / target_pct <= stage.MAX_ADAPTIVE_BARRIER_RATIO + 1e-9

    guard_entries = [e for e in ctx.cognition.relevant_knowledge if e.get("type") == "tp_sl_ratio_guard"]
    assert len(guard_entries) == 1
    assert guard_entries[0]["data"]["widened_target_pct"] == round(target_pct, 6)


def test_normal_ratio_is_not_touched():
    from engines.cognitive_pipeline import RiskTargetStage

    ctx = _base_ctx()
    stage = RiskTargetStage()
    stage.execute(ctx)

    guard_entries = [e for e in ctx.cognition.relevant_knowledge if e.get("type") == "tp_sl_ratio_guard"]
    assert guard_entries == []


def test_record_persists_tp_sl_ratio_guard_entries_into_agent_opinions():
    recorder = DecisionRecorder()
    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT"}, decision={"proposed_size": 0.5})
    event = recorder.record(
        ctx, [],
        tp_sl_ratio_guard_entries=[{"stop_pct": 0.05, "pre_guard_target_pct": 0.003, "widened_target_pct": 0.0091}],
    )
    matches = [o for o in event.agent_opinions if o.get("type") == "tp_sl_ratio_guard"]
    assert len(matches) == 1
    assert matches[0]["data"]["widened_target_pct"] == 0.0091


def test_recording_stage_extracts_tp_sl_ratio_guard_from_relevant_knowledge():
    from contracts.belief import Belief
    from engines.cognitive_pipeline import RecordingStage

    stage = RecordingStage()
    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT"})
    ctx.cognition.relevant_knowledge.append({
        "type": "tp_sl_ratio_guard",
        "data": {"stop_pct": 0.05, "pre_guard_target_pct": 0.003, "widened_target_pct": 0.0091},
    })
    belief = Belief(direction="SHORT", strength=0.8, uncertainty=0.2)

    event = stage.execute(ctx, belief, [])

    matches = [o for o in event.agent_opinions if o.get("type") == "tp_sl_ratio_guard"]
    assert len(matches) == 1
    assert matches[0]["data"]["widened_target_pct"] == 0.0091
