from fastapi import APIRouter, Depends

from config import get_settings
from contracts.auth import Role
from market_data.ingestion.data_provider import get_ohlcv_provider
from services.auth_service import AuthContext, require_role
from services.cognitive_engine import CognitiveEngine
from services.orchestrator import _get_risk_bars_cached, build_cognitive_context

router = APIRouter(prefix="/cognitive", tags=["cognitive"])

engine = CognitiveEngine()


@router.post("/run")
def run_cognitive_cycle(
    symbol: str | None = None,
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    settings = get_settings()
    symbol = symbol or settings.DEFAULT_SYMBOL

    # Faz 224 review bulgusu (E): bu endpoint önceden services/orchestrator.
    # py::_build_context()'ten TAMAMEN ayrı, kendi context'ini kuran ikinci
    # bir giriş noktasıydı (gap #15 ile aynı desen: iki entrypoint bağımsızca
    # aynı işi yapıyor, biri düzeltilince diğeri unutulabiliyor — gerçek bir
    # örneği: Faz 206'nın proposed_size düzeltmesi orchestrator.py'de
    # yapılıp burada unutulmuştu). Artık build_cognitive_context() — TEK
    # gerçek kaynak — kullanılıyor, ikinci bir kopya yok.
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        settings_repo = AppSettingsRepository(session)
        timeframe = settings_repo.get("candle_timeframe")
        lookback = int(settings_repo.get("candle_lookback"))

    provider = get_ohlcv_provider()
    data = provider.get_ohlcv(symbol, timeframe, limit=lookback)
    if not data:
        # build_cognitive_context() gerçek OHLCV verisi (data[-1]) gerektirir
        # — burada yok, ama risk state/limitler yine de yüklenmeli (Gap #15
        # ile aynı fail-closed davranış: limit hiç set edilmemişse RiskEngine
        # MISSING_LIMIT ile reddeder, bu doğru/kasıtlı davranış).
        from contracts.context import CognitiveCycleContext
        from database.repositories.risk_limit_repository import load_active_limits
        from services.risk_state import load_position_risk_state

        ctx = CognitiveCycleContext()
        ctx.market.symbol = symbol
        ctx.market.timeframe = timeframe
        ctx.risk.limits = load_active_limits()
        risk_state = load_position_risk_state(symbol=symbol)
        ctx.risk.trading_mode = risk_state["trading_mode"]
        ctx.risk.open_position_count = risk_state["open_position_count"]
        ctx.risk.max_concurrent_positions = risk_state["max_concurrent_positions"]
        ctx.risk.capital_used_pct = risk_state["capital_used_pct"]
        ctx.risk.max_capital_pct = risk_state["max_capital_pct"]
        ctx.risk.seconds_since_last_trade = risk_state["seconds_since_last_trade"]
        ctx.risk.min_seconds_between_trades = risk_state["min_seconds_between_trades"]
        ctx.risk.ai_enabled = risk_state["ai_enabled"]
        ctx.risk.consecutive_losses = risk_state["consecutive_losses"]
        ctx.risk.kill_switch_consecutive_losses = risk_state["kill_switch_consecutive_losses"]
    else:
        # Faz 317-sonrası — trade_horizon ayarı kaldırıldı (bkz. services/
        # orchestrator.py::propose üstündeki AYNI not), sabit 4h. Bu
        # endpoint orchestrator.propose()'un (kısa-vadeli) manuel tetikleme
        # karşılığı, aynı risk tabanını kullanmalı.
        risk_data = _get_risk_bars_cached(provider, symbol, timeframe="4h", limit=60)
        ctx = build_cognitive_context(symbol, timeframe, data, daily_data=risk_data)

    result = engine.run(ctx)

    return {
        "cycle_id": str(result.cycle_id),
        "action": str(result.decision.action),
        "direction": result.decision.proposed_direction,
        "confidence": result.decision.confidence,
        "uncertainty": result.decision.uncertainty,
        "knowledge": result.cognition.relevant_knowledge,
        "risk_verdict": result.risk.evaluation.verdict,
        # Faz 268x — services/orchestrator.py::finalize_proposal ile aynı
        # tutarlı format (kod + gerçek mesaj) — sadece kod, "869 open >=
        # limit 10" gibi asıl bilgiyi kaybediyordu.
        "risk_reasons": [f"{r.code}: {r.message}" for r in result.risk.evaluation.reasons],
    }
