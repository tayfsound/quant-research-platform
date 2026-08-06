"""End-to-end cognitive loop orchestrator — v1.1 trusted paper cycle."""
from typing import Any
from database.repositories.risk_limit_repository import load_active_limits
from services.risk_state import load_position_risk_state
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

def build_cognitive_context(symbol: str, timeframe: str, data) -> CognitiveCycleContext:
    """Faz 224 review bulgusu (E): bu mantık önceden HEM burada (özel
    _build_context metodu olarak) HEM DE api/rest/cognitive.py'de
    (run_cognitive_cycle içinde) bağımsızca tekrarlanıyordu — "gap #15 ile
    aynı desen: iki entrypoint aynı işi bağımsız yapıyor, biri
    düzeltilince diğeri unutulabiliyor" (Faz 214'ün kendi yorumu, gerçek
    bir örneği: proposed_size düzeltmesi orchestrator.py'de yapılıp
    cognitive.py'de unutulmuştu). Artık TEK gerçek kaynak — her iki
    entrypoint de bunu çağırıyor."""
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
    # Gap #15: bu alan önceden boş bir dict'ti, bu yüzden RiskEngine her
    # cycle'ı MISSING_LIMIT ile reddediyordu.
    ctx.risk.limits = load_active_limits()

    # Faz 188: test/live modu + gerçek açık pozisyon sayısı/sermaye
    # yüzdesi — RiskEngine (ön) ve RiskGateStage (son) bunları kullanıyor.
    risk_state = load_position_risk_state(symbol=symbol)
    ctx.risk.trading_mode = risk_state["trading_mode"]
    ctx.risk.open_position_count = risk_state["open_position_count"]
    ctx.risk.max_concurrent_positions = risk_state["max_concurrent_positions"]
    ctx.risk.capital_used_pct = risk_state["capital_used_pct"]
    ctx.risk.max_capital_pct = risk_state["max_capital_pct"]
    ctx.risk.seconds_since_last_trade = risk_state["seconds_since_last_trade"]
    ctx.risk.min_seconds_between_trades = risk_state["min_seconds_between_trades"]
    ctx.risk.ai_enabled = risk_state["ai_enabled"]

    # Faz 211: her işlem, sermayenin (starting_capital * max_capital_pct)
    # eşit dilimlere bölünmüş (max_concurrent_positions) GERÇEK bir $
    # notional bütçesi hedefliyor; birim sayısı bu bütçenin güncel fiyata
    # bölünmesiyle çıkıyor — pahalı/ucuz varlıklar artık aynı gerçek $
    # riskini taşıyor.
    current_price = data[-1].close
    capital_per_trade = (
        risk_state["starting_capital"] * risk_state["max_capital_pct"]
        / max(risk_state["max_concurrent_positions"], 1)
    )
    ctx.decision.proposed_size = capital_per_trade / current_price if current_price else 0.0

    return ctx


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

    def propose(self, symbol: str) -> dict | None:
        """Faz 199: 'öner ama henüz açma' — services/portfolio_fusion.py'yi
        gerçekten bağlamak için run_cycle()'dan ayrıldı. Birden fazla
        sembolün eşzamanlı önerisini GERÇEKTEN açmadan önce portföy-seviyesi
        VaR'a göre ölçeklendirebilmek gerekiyor (bkz. run_portfolio_aware_
        cycle) — run_cycle() hâlâ tek-sembol, anında-finalize eski
        davranışını koruyor, regresyon yok."""
        # Faz 214: kullanıcı isteği — mum aralığı/geçmiş pencere artık
        # sabit değil, app_settings'ten okunuyor (varsayılan öncekiyle
        # birebir aynı: 1m, 100 bar — regresyon yok).
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            timeframe = settings_repo.get("candle_timeframe")
            lookback = int(settings_repo.get("candle_lookback"))

        data = self.data_provider.get_ohlcv(symbol, timeframe, limit=lookback)
        if not data:
            return None

        ctx = self._build_context(symbol, timeframe, data)
        ctx = self.engine.run(ctx, persist=False)

        market_price = data[-1].close
        direction = ctx.decision.proposed_direction if ctx.decision.proposed_direction else "NEUTRAL"
        size = ctx.decision.final_size if ctx.decision.final_size else 0.0

        if direction != "NEUTRAL" and size > 0:
            result = self.fill_engine.simulate({"direction": direction, "size": size}, market_price)
            filled_price, fee = result.filled_price, result.fee
        else:
            filled_price, fee = market_price, 0.0

        # Faz 187: filled_price'ı ctx'e yaz ki RecordingStage (finalize()
        # içinde) gerçek entry_price'ı persist edebilsin.
        ctx.decision.filled_price = filled_price

        return {"ctx": ctx, "data": data, "fee": fee, "direction": direction}

    def finalize_proposal(self, proposal: dict, seed: int = 42) -> dict[str, Any]:
        """propose()'un çıktısını (portföy fusion varsa ctx.decision.
        final_size değişmiş olabilir) al, gerçekten kaydet/aç. run_cycle()
        ile aynı sözlük şeklini döndürür."""
        ctx = proposal["ctx"]
        data = proposal["data"]
        fee = proposal["fee"]
        direction = proposal["direction"]
        filled_price = ctx.decision.filled_price
        size = ctx.decision.final_size or 0.0

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
            "symbol": ctx.market.symbol,
        }

    def run_portfolio_aware_cycle(self, symbols: list[str], seed: int = 42) -> list[dict[str, Any]]:
        """Faz 199: services/portfolio_fusion.py + risk/limits/portfolio.py'yi
        (yazılmış, test edilmiş ama hiçbir yerden çağrılmayan portföy VaR
        motoru) gerçekten bağlıyor. Aynı cycle'da 2+ sembol eşzamanlı yönlü
        öneri üretirse, GERÇEKTEN açılmadan önce gerçek kovaryans matrisiyle
        (korelasyon dahil) hesaplanan portföy VaR'ı kullanıcının belirlediği
        sınırı (max_portfolio_var_pct) aşarsa önerilen büyüklükler orantılı
        şekilde küçültülüyor — "sinyal limitleri gevşetemez" kuralı burada
        da geçerli, sadece küçültebiliyor."""
        proposals: dict[str, dict] = {}
        for sym in symbols:
            p = self.propose(sym)
            if p is not None:
                proposals[sym] = p

        directional = {
            sym: p for sym, p in proposals.items()
            if p["direction"] in ("LONG", "SHORT") and (p["ctx"].decision.final_size or 0) > 0
        }

        if len(directional) >= 2:
            self._apply_portfolio_fusion(directional)

        return [
            self.finalize_proposal(proposals[sym], seed=seed) if sym in proposals
            else {"symbol": sym, "direction": "NEUTRAL", "error": "no_data", "memory_size": len(self.memory.memory)}
            for sym in symbols
        ]

    def _apply_portfolio_fusion(self, directional: dict[str, dict]) -> None:
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory
        from risk.limits.portfolio import PortfolioRiskEngine
        from services.portfolio_fusion import PortfolioFusionStage

        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            starting_capital = float(settings_repo.get("starting_capital"))
            max_var_pct = float(settings_repo.get("max_portfolio_var_pct"))

        returns: dict[str, list[float]] = {}
        proposed_sizes: dict[str, float] = {}
        for sym, p in directional.items():
            closes = [bar.close for bar in p["data"]]
            rets = [
                (closes[i] - closes[i - 1]) / closes[i - 1]
                for i in range(1, len(closes)) if closes[i - 1]
            ]
            if len(rets) < 2:
                continue
            returns[sym] = rets
            sign = 1.0 if p["direction"] == "LONG" else -1.0
            proposed_sizes[sym] = sign * (p["ctx"].decision.final_size or 0.0)

        if len(returns) < 2:
            return

        min_len = min(len(v) for v in returns.values())
        returns = {s: v[-min_len:] for s, v in returns.items()}
        proposed_sizes = {s: v for s, v in proposed_sizes.items() if s in returns}

        fusion = PortfolioFusionStage(PortfolioRiskEngine())
        result = fusion.fuse(
            proposed_sizes=proposed_sizes,
            returns=returns,
            portfolio_value=starting_capital,
            max_var=starting_capital * max_var_pct,
        )

        if result.scaled_down:
            for sym, signed_size in result.final_sizes.items():
                directional[sym]["ctx"].decision.final_size = abs(signed_size)

    def _build_context(self, symbol: str, timeframe: str, data) -> CognitiveCycleContext:
        # Faz 224 review (E): gövde module-level build_cognitive_context()'e
        # taşındı — api/rest/cognitive.py da artık AYNI fonksiyonu çağırıyor,
        # iki bağımsız kopya kalmadı.
        return build_cognitive_context(symbol, timeframe, data)

    def run_cycle(self, seed: int = 42, symbol: str | None = None) -> dict[str, Any]:
        settings = get_settings()
        symbol = symbol or settings.DEFAULT_SYMBOL

        proposal = self.propose(symbol)
        if proposal is None:
            return {"direction": "NEUTRAL", "error": "no_data", "memory_size": len(self.memory.memory)}

        return self.finalize_proposal(proposal, seed=seed)
