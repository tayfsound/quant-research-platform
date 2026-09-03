"""Faz 409 — kullanıcı bulgusu (2026-09-03, ölçüm stabilitesi/macro
araştırması sırasında bulundu): RiskTargetStage'in TP/SL Confluence
etiketi ("tp_sl_confluence"/"sl_confluence") GERÇEKTEN çalışıyordu
(fiyatları doğru ayarlıyordu) ama RecordingStage'in çıkarım listesinde
hiç yoktu — decision_fusion/market_state ile AYNI görünürlük deseni
buraya hiç eklenmemişti. "Hedef/stop neden bu kadar sıkı?" sorusunun
cevabı DB'de hiç yoktu. Bu testler hem DecisionRecorder.record() hem
RecordingStage.execute() seviyesinde etiketin GERÇEKTEN agent_
contributions'a ulaştığını doğruluyor."""
from contracts.context import CognitiveCycleContext
from services.decision_recorder import DecisionRecorder


def test_record_persists_tp_sl_confluence_entries_into_agent_opinions():
    recorder = DecisionRecorder()
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT"},
        decision={"proposed_size": 0.5},
    )
    event = recorder.record(
        ctx, [],
        tp_sl_confluence_entries=[{"zone": {"level": 101.5}, "adjusted_target_pct": 0.008}],
    )
    matches = [o for o in event.agent_opinions if o.get("type") == "tp_sl_confluence"]
    assert len(matches) == 1
    assert matches[0]["data"]["adjusted_target_pct"] == 0.008


def test_record_persists_sl_confluence_entries_into_agent_opinions():
    recorder = DecisionRecorder()
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT"},
        decision={"proposed_size": 0.5},
    )
    event = recorder.record(
        ctx, [],
        sl_confluence_entries=[{"zone": {"level": 95.3}, "adjusted_stop_pct": 0.047}],
    )
    matches = [o for o in event.agent_opinions if o.get("type") == "sl_confluence"]
    assert len(matches) == 1
    assert matches[0]["data"]["adjusted_stop_pct"] == 0.047


def test_recording_stage_extracts_tp_sl_confluence_from_relevant_knowledge():
    """Uçtan uca: RiskTargetStage'in relevant_knowledge'a bıraktığı ETİKET
    (gerçek üretim kodunun AYNI formatı) RecordingStage tarafından doğru
    çıkarılıp DecisionRecorder.record()'a iletiliyor mu."""
    from contracts.belief import Belief
    from engines.cognitive_pipeline import RecordingStage

    stage = RecordingStage()
    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT"})
    ctx.cognition.relevant_knowledge.append({
        "type": "tp_sl_confluence",
        "data": {"zone": {"level": 101.5, "method_count": 2}, "adjusted_target_pct": 0.012},
    })
    ctx.cognition.relevant_knowledge.append({
        "type": "sl_confluence",
        "data": {"zone": {"level": 95.3, "method_count": 2}, "adjusted_stop_pct": 0.046},
    })
    belief = Belief(direction="LONG", strength=0.8, uncertainty=0.2)

    event = stage.execute(ctx, belief, [])

    tp_matches = [o for o in event.agent_opinions if o.get("type") == "tp_sl_confluence"]
    sl_matches = [o for o in event.agent_opinions if o.get("type") == "sl_confluence"]
    assert len(tp_matches) == 1
    assert tp_matches[0]["data"]["adjusted_target_pct"] == 0.012
    assert len(sl_matches) == 1
    assert sl_matches[0]["data"]["adjusted_stop_pct"] == 0.046
