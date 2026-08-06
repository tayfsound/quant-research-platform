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
