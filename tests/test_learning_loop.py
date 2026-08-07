"""Learning Loop testleri.

Faz 211 temizliği: test_process_outcome kaldırıldı — LearningLoop.
process_outcome()/OutcomeTracker.attach_outcome() silindi (hiç
başlatılmayan PendingOutcomeTracker'ın tek tüketicisiydi, ve zaten
agent_opinions=[] ile kırıktı). Gerçek pozisyon kapanışlarının öğrenme
döngüsüne geri beslenmesi artık services/position_closer.py'de."""


def test_engine_persist_and_learn_with_outcome():
    """CognitiveEngine._persist_and_learn ctx.outcome varsa learning calistirmali (P1-12)."""
    from unittest.mock import patch, MagicMock
    from contracts.outcome import TradeOutcome
    from services.cognitive_engine import CognitiveEngine

    engine = CognitiveEngine()
    ctx = MagicMock()
    ctx.outcome = TradeOutcome(pnl=100, win=True, decision="LONG", confidence_at_decision=0.8)
    event = MagicMock()
    event.confidence = 0.8
    event.final_action = "ENTER_LONG"
    event.agent_opinions = []
    event.market_snapshot = {}

    with patch.object(engine.learning_loop, "record") as mock_record:
        with patch.object(engine.weight_optimizer, "optimize", return_value={}):
            with patch.object(engine.weight_repository, "get_latest", return_value=None):
                with patch.object(engine.weight_repository, "save"):
                    with patch("database.repositories.decision_persistor.DecisionPersistor.persist"):
                        engine._persist_and_learn(event, ctx)
                        mock_record.assert_called_once()


def test_apply_feedback_scores_each_agent_by_own_direction_and_tags_source(tmp_path):
    """Faz 248: kritik bulgu — services/orchestrator.py::finalize_proposal
    (ForwardOutcome ile AYNI cycle'da geriye dönük hesap yapan, gerçek
    pozisyon kapanışından TAMAMEN BAĞIMSIZ bir yol) hâlâ HER trading
    cycle'da bu yolu tetikliyordu — modül docstring'inin "artık
    position_closer.py'de" varsayımının aksine. Bu yol Faz 211 (blanket
    was_correct) ve Faz 245 (WAIT ödüllendirmesi) düzeltmelerini hiç
    almamıştı. Bu test, her ajanın KENDİ yönüne göre puanlandığını, WAIT
    diyen ajanın hiç kaydedilmediğini ve source="forward_estimate" ile
    açıkça etiketlendiğini kanıtlıyor."""
    from unittest.mock import MagicMock

    from services.agent_memory import AgentMemory
    from services.learning_loop import LearningLoop

    loop = LearningLoop()
    loop.agent_memory = AgentMemory(storage_path=str(tmp_path / "agent_memory_history"))

    event = MagicMock()
    event.confidence = 0.6
    event.final_action = "LONG"
    event.symbol = "BTCUSDT"
    event.market_snapshot = {"raw_snapshot": {"trend": "up"}}
    event.agent_opinions = [
        {"domain": "technical", "direction": "LONG", "confidence": 0.7},
        {"domain": "macro", "direction": "SHORT", "confidence": 0.5},
        {"domain": "sentiment", "direction": "WAIT", "confidence": 0.2},
    ]

    # İşlem KAZANDI (pnl > 0): LONG diyen technical doğru, SHORT diyen
    # macro yanlış, WAIT diyen sentiment hiç kaydedilmemeli.
    loop._apply_feedback(event, was_correct=True, pnl=50.0)

    technical_records = loop.agent_memory._records.get("technical", [])
    macro_records = loop.agent_memory._records.get("macro", [])
    assert len(technical_records) == 1
    assert technical_records[0].was_correct is True
    assert technical_records[0].source == "forward_estimate"
    assert len(macro_records) == 1
    assert macro_records[0].was_correct is False
    assert "sentiment" not in loop.agent_memory._records or len(loop.agent_memory._records["sentiment"]) == 0
