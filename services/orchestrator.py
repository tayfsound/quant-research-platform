"""End-to-end cognitive loop orchestrator — v1.1 trusted paper cycle."""
from typing import Any
from database.repositories.risk_limit_repository import load_active_limits
from market_data.ingestion.data_provider import get_ohlcv_provider, OHLCVProvider
from market_data.features.signal_engine import (
    compute_pattern_signals,
    compute_quant_signals,
    compute_technical_signals,
)
from simulator.fill_engine import FillEngine
from ml.training.replay_memory import ReplayMemory
from services.cognitive_engine import CognitiveEngine
from services.forward_outcome import ForwardOutcome
from services.decision_recorder import DecisionRecorder
from config import get_settings
from contracts.context import CognitiveCycleContext

class CognitiveOrchestrator:
    def __init__(
        self,
        data_provider: OHLCVProvider | None = None,
        max_position_size: float = 1.0,
        max_drawdown: float = 0.15,
        current_drawdown: float = 0.0,
    ):
        self.engine = CognitiveEngine()
        self.fill_engine = FillEngine()
        self.memory = ReplayMemory(capacity=10000)
        self.forward = ForwardOutcome(bars_forward=10)
        self.recorder = DecisionRecorder()
        self.data_provider = data_provider or get_ohlcv_provider()
        self.max_position_size = max_position_size
        self.max_drawdown_limit = max_drawdown
        self.current_drawdown = current_drawdown

    def run_cycle(self, seed: int = 42, symbol: str | None = None) -> dict[str, Any]:
        settings = get_settings()
        symbol = symbol or settings.DEFAULT_SYMBOL
        timeframe = settings.DEFAULT_TIMEFRAME
        
        data = self.data_provider.get_ohlcv(symbol, timeframe, limit=100)
        if not data:
            return {"direction": "NEUTRAL", "error": "no_data", "memory_size": len(self.memory.memory)}
        
        # Build cognitive context
        ctx = CognitiveCycleContext()
        ctx.market.symbol = symbol
        ctx.market.timeframe = timeframe

        # Kritik bulgu (2026-08-05): buradan sadece ham rsi/ema/macd sayıları
        # geçiyordu — TechnicalAgent'ın gerçekten skorladığı trend/momentum/
        # market_structure/ema_alignment/volatility_regime alanlarını HİÇBİR
        # kod üretmiyordu (hep varsayılan/nötr), ve Pattern/Quant ajanları da
        # (bu oturumda eklenen) üretimde tamamen kör çalışıyordu. Artık
        # gerçek OHLCV geçmişinden hesaplanıyor — bkz. market_data/features/
        # signal_engine.py.
        technical_signals = compute_technical_signals(data)
        pattern_signals = compute_pattern_signals(data)
        quant_signals = compute_quant_signals(data)

        ctx.market.features = {**technical_signals, **quant_signals}
        ctx.market.raw_snapshot = {
            "close": data[-1].close,
            "volume": data[-1].volume,
            "high": data[-1].high,
            "low": data[-1].low,
            **pattern_signals,
        }
        # Gap #15: same fix as api/rest/cognitive.py — this used to be an
        # empty dict, so RiskEngine rejected every cycle with MISSING_LIMIT
        # regardless of what self.max_position_size/max_drawdown_limit said
        # (those constructor args were never actually wired to the risk gate).
        ctx.risk.limits = load_active_limits()

        # Run cognitive engine (council + meta + fusion + risk)
        ctx = self.engine.run(ctx, persist=False)
        
        market_price = data[-1].close
        direction = ctx.decision.proposed_direction if ctx.decision.proposed_direction else "NEUTRAL"
        size = ctx.decision.final_size if ctx.decision.final_size else 0.0
        
        # Execution simulation
        if direction != "NEUTRAL" and size > 0:
            decision = {"direction": direction, "size": size}
            result = self.fill_engine.simulate(decision, market_price)
            filled_price = result.filled_price
            fee = result.fee
        else:
            filled_price = market_price
            fee = 0.0

        # Faz 187: filled_price'ı ctx'e yaz ki RecordingStage (aşağıdaki
        # finalize() içinde çalışır) gerçek entry_price'ı persist edebilsin —
        # pozisyon burada GERÇEKTEN açılıyor, kapanışı services/
        # position_closer.py gerçek zaman geçtikten sonra yapıyor.
        ctx.decision.filled_price = filled_price

        # Bu anlık "n-bar forward" hesaplaması iki farklı amaca hizmet
        # ediyor ve bunları birbirinden ayırmak önemli:
        # 1) ctx.outcome (TradeOutcome) — CognitiveEngine.finalize()'ın
        #    memory_engine/learning_loop/weight_optimizer'ı tetiklemek için
        #    HER cycle'da ihtiyaç duyduğu öğrenme sinyali (ctx.outcome is
        #    None ise learning tamamen atlanıyor — bkz. cognitive_engine.py).
        #    Bunu kaldırmak öğrenme döngüsünü tamamen kırar (gerçek bulgu,
        #    tests/test_memory_engine_wiring.py ile yakalandı).
        # 2) decisions.status/entry_price/exit_price/opened_at/closed_at —
        #    Faz 187'nin GERÇEK, zaman-bazlı pozisyon yaşam döngüsü. Bu ikisi
        #    kasıtlı olarak birbirinden bağımsız: decisions.outcome kolonu
        #    artık kayıt anında hep boş kalıyor (DecisionRecorder), pozisyon
        #    gerçekten services/position_closer.py ile kapanana kadar.
        outcome = self.forward.calculate(filled_price, direction, data)
        pnl = outcome["pnl"] - fee
        win = outcome["win"]
        from contracts.outcome import TradeOutcome
        ctx.outcome = TradeOutcome(
            pnl=outcome["pnl"],
            win=outcome["win"],
            decision=direction,
            confidence_at_decision=ctx.decision.confidence,
        )

        # REMOVED: self.recorder.record(ctx, [], None)
        # Engine RecordingStage zaten kaydediyor -- cift kayit yok (P1-8)
        
        # Memory (sadece risk-onaylı)
        ctx = self.engine.finalize(ctx)

        if direction != "NEUTRAL" and size > 0:
            self.memory.add({
                "decision_id": f"cycle_{seed}",
                "features": ctx.market.features,
                "label": 1 if win else 0,
                "pnl": pnl,
                "quality_score": 0.8,
                "timestamp": data[-1].timestamp.isoformat(),
                "direction": direction,
            })
        
        return {
            "direction": direction,
            "size": size,
            "filled_price": filled_price,
            "fee": fee,
            "pnl": pnl,
            "win": win,
            "memory_size": len(self.memory.memory),
            "risk_verdict": ctx.risk.evaluation.verdict if ctx.risk.evaluation else "unknown",
            "risk_reasons": [str(r) for r in ctx.risk.evaluation.reasons] if ctx.risk.evaluation else [],
            "action": ctx.decision.action.value if ctx.decision.action else "WAIT",
            "confidence": ctx.decision.confidence,
            "features": ctx.market.features,
            "symbol": symbol,
        }
