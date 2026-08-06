"""Faz 212: gerçek bulgu — DecisionFusion.evaluate()'in ret nedeni
(Negative EV / min_profit_target_pct) ctx.cognition.relevant_knowledge'a
yazılıyordu ama decisions.agent_contributions'a hiç aktarılmıyordu.
"Neden reddedildi?" sorusunun cevabı DB'de yoktu — canlı kod tekrar
çalıştırılmadan görülemiyordu (bu turda gerçekten yaşandı: min_profit_
target_pct'in 30 sinyalden 27'sini elediği, sadece manuel reprodüksiyonla
anlaşılabildi)."""
from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.decision_recorder import DecisionRecorder


class _FakeRiskEvaluation:
    verdict = "approved"

    def model_dump(self):
        return {"verdict": "approved", "reasons": []}


class _FakeMarket:
    symbol = "FUSIONTEST"
    timeframe = "1m"
    features = {}
    raw_snapshot = {"close": 100.0}


class _FakeDecision:
    proposed_direction = "LONG"
    final_action = "LONG"
    final_size = 0.0
    confidence = 0.4
    filled_price = None


class _FakeRisk:
    evaluation = _FakeRiskEvaluation()


class _FakeCtx:
    def __init__(self, cycle_id):
        self.cycle_id = cycle_id
        self.timestamp = __import__("datetime").datetime.now(__import__("datetime").UTC)
        self.market = _FakeMarket()
        self.decision = _FakeDecision()
        self.risk = _FakeRisk()


def test_decision_fusion_rejection_reason_is_persisted_in_agent_contributions():
    from uuid import uuid4
    ctx = _FakeCtx(uuid4())

    recorder = DecisionRecorder()
    event = recorder.record(
        ctx,
        opinions=[],
        belief=None,
        decision_fusion_entries=[{"rejection": "Target below min_profit_target_pct", "target_pct": 0.0008}],
    )

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))

    assert row is not None
    fusion_entries = [i for i in row["agent_contributions"] if i.get("type") == "decision_fusion"]
    assert len(fusion_entries) == 1
    assert fusion_entries[0]["data"]["rejection"] == "Target below min_profit_target_pct"
