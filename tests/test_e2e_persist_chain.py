"""E2E: full cycle → DB persist + belief + weight chain.

Faz 250: kritik bulgu — engine.finalize()'ın ctx.outcome'ı ForwardOutcome'ın
aynı cycle'da geriye dönük hesapladığı düşük kaliteli bir "tahmin", gerçek
bir pozisyon kapanışı değil. Kullanıcı kararı: bu sinyal AgentMemory'yi/
ağırlıkları hiç beslememeli — _persist_and_learn artık kasıtlı bir no-op."""
from unittest.mock import patch


class FakeLimit:
    value = 10.0
    def verify(self, secret):
        return True

def test_full_cycle_persist_belief_weight_chain():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from contracts.context import CognitiveCycleContext
        from contracts.outcome import TradeOutcome
        from services.cognitive_engine import CognitiveEngine

        engine = CognitiveEngine()
        ctx = CognitiveCycleContext()
        ctx.market.symbol = "BTCUSDT"
        ctx.decision.proposed_direction = "LONG"
        ctx.decision.confidence = 0.8
        ctx.risk.limits = {"max_position_size": FakeLimit()}
        ctx.risk.current_drawdown = 0.0

        with patch.object(engine.record_stage.recorder.persistor, "persist") as mock_db:
            with patch("services.memory_service.MemoryService.store_belief") as mock_belief:
                ctx = engine.run(ctx, persist=True)
                mock_db.assert_called_once()
                mock_belief.assert_called_once()

        ctx.outcome = TradeOutcome(pnl=100, win=True, decision="LONG", confidence_at_decision=0.8)
        with patch.object(engine.learning_loop, "record") as mock_learn:
            with patch.object(engine.weight_optimizer, "optimize") as mock_weight:
                mock_weight.return_value = {"technical": 1.2}
                engine.finalize(ctx)
                mock_learn.assert_not_called()
                mock_weight.assert_not_called()
