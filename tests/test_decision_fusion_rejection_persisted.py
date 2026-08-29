"""Faz 212: gerçek bulgu — DecisionFusion.evaluate()'in ret nedeni
(Negative EV / min_profit_target_pct) ctx.cognition.relevant_knowledge'a
yazılıyordu ama decisions.agent_contributions'a hiç aktarılmıyordu.
"Neden reddedildi?" sorusunun cevabı DB'de yoktu — canlı kod tekrar
çalıştırılmadan görülemiyordu (bu turda gerçekten yaşandı: min_profit_
target_pct'in 30 sinyalden 27'sini elediği, sadece manuel reprodüksiyonla
anlaşılabildi)."""
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


class _FakeCtxWithCognition(_FakeCtx):
    """Faz 370-devam — cognition.relevant_knowledge taşıyan gerçekçi ctx.
    engines/cognitive_pipeline.py::CognitiveCycleContext'in gerçek şeklini
    taklit eder (basit bir namespace, sadece bu testin ihtiyacı olan
    kısım)."""
    def __init__(self, cycle_id):
        super().__init__(cycle_id)

        class _Cognition:
            relevant_knowledge = []

        self.cognition = _Cognition()


def test_council_and_final_decision_lineage_are_persisted_separately_even_when_they_diverge():
    """Faz 370-devam — KRİTİK canlı bulgu regresyon testi (gerçek olay:
    TRUMPUSDT — debate_result SHORT/0.429 derken persist edilen
    decisions.direction=LONG, confidence=0.7939 çıktı, "aynı karar
    nesnesinden gelmiyormuş" gibi göründü). Council'in ham oyu (debate_
    result) ile MetaStage'in ACT/REDUCE/WAIT kararını verdiği andaki
    confidence'ın (pre_fusion_snapshot) ve nihai (DecisionFusion sonrası)
    direction/confidence'ın KASITLI OLARAK FARKLI kurgulandığı bir
    senaryoda, üçünün de ayrı ayrı, doğru şekilde persist edildiğini —
    ve bu ayrımın artık SQL ile (JSON'a inmeden) görülebildiğini
    doğrular."""
    from uuid import uuid4
    ctx = _FakeCtxWithCognition(uuid4())
    ctx.decision.proposed_direction = "LONG"  # MetaStage'in belirlediği nihai yön (weight-snapshot ağırlıklı)
    ctx.decision.confidence = 0.7939  # DecisionFusion'ın SONRADAN yeniden kalibre ettiği değer
    ctx.cognition.relevant_knowledge = [
        {
            "type": "pre_fusion_snapshot",
            "data": {"meta_decision": "ACT", "pre_fusion_confidence": 0.8419, "belief_direction": "LONG"},
        },
    ]

    recorder = DecisionRecorder()
    event = recorder.record(
        ctx,
        opinions=[],
        belief=None,
        debate_result={"final_direction": "SHORT", "final_confidence": 0.429},
        decision_fusion_entries=[{"rejection": "Negatif beklenen değer (EV)", "ev": 0.0}],
    )

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(event.id))

    assert row is not None
    # Council'in ham oyu (agent_debate.py'nin kendi, benching'ten habersiz sentezi)
    assert row["council_direction"] == "SHORT"
    assert row["council_confidence"] == 0.429
    # MetaStage'in ACT/REDUCE/WAIT kararı VE o andaki confidence — DecisionFusion'ın
    # sonradan üzerine yazacağı değerden ÖNCEKİ, gerçekten karar verilen an.
    assert row["meta_decision"] == "ACT"
    assert row["pre_fusion_confidence"] == 0.8419
    # Nihai (persist edilen) direction/confidence — MetaStage'in yönü + DecisionFusion'ın kalibrasyonu.
    assert row["direction"] == "LONG"
    assert row["confidence"] == 0.7939
    # DecisionFusion'ın EV/ret gerekçesi artık ayrı, sorgulanabilir sütunlarda.
    assert row["final_ev"] == 0.0
    assert row["rejection_reason"] == "Negatif beklenen değer (EV)"
    # Üç katman burada KASITLI olarak farklı — testin asıl amacı bu ayrımın
    # gizlenmeden, açıkça persist edildiğini kanıtlamak.
    assert row["council_direction"] != row["direction"]
