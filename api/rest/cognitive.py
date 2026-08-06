from fastapi import APIRouter, Depends

from config import get_settings
from contracts.auth import Role
from contracts.context import CognitiveCycleContext
from database.repositories.risk_limit_repository import load_active_limits
from services.risk_state import load_position_risk_state
from market_data.features.signal_engine import (
    compute_pattern_signals,
    compute_quant_signals,
    compute_technical_signals,
)
from market_data.ingestion.data_provider import get_ohlcv_provider
from services.auth_service import AuthContext, require_role
from services.cognitive_engine import CognitiveEngine

router = APIRouter(prefix="/cognitive", tags=["cognitive"])

engine = CognitiveEngine()


@router.post("/run")
async def run_cognitive_cycle(
    symbol: str | None = None,
    user: AuthContext = Depends(require_role(Role.OPERATOR)),
):
    settings = get_settings()
    symbol = symbol or settings.DEFAULT_SYMBOL

    # Kritik bulgu (2026-08-05): bu endpoint tamamen boş bir context
    # oluşturuyordu — hiçbir market verisi yok, hiçbir agent gerçek bir şey
    # göremiyordu. CognitiveOrchestrator.run_cycle()'ın zaten yaptığı gibi
    # gerçek OHLCV geçmişi çekilip gerçek sinyaller hesaplanıyor.
    #
    # Faz 214: burası services/orchestrator.py::_build_context()'ten TAMAMEN
    # ayrı, kendi context'ini kuran ikinci bir giriş noktası (gap #15 ile
    # aynı desen: iki entrypoint bağımsızca aynı işi yapıyor, biri
    # düzeltilince diğeri unutulabiliyor). Bu yüzden Faz 206'nın "proposed_
    # size hiç set edilmiyordu" bug'ı BURADA hâlâ vardı — orchestrator.py'de
    # düzeltilirken bu endpoint'e hiç dokunulmamış. mum aralığı/pencere de
    # artık sabit değil, app_settings'ten (candle_timeframe/candle_lookback).
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        settings_repo = AppSettingsRepository(session)
        timeframe = settings_repo.get("candle_timeframe")
        lookback = int(settings_repo.get("candle_lookback"))

    ctx = CognitiveCycleContext()
    ctx.market.symbol = symbol
    ctx.market.timeframe = timeframe
    data = get_ohlcv_provider().get_ohlcv(symbol, timeframe, limit=lookback)
    if data:
        ctx.market.features = {**compute_technical_signals(data), **compute_quant_signals(data)}
        ctx.market.raw_snapshot = {
            "close": data[-1].close,
            "volume": data[-1].volume,
            "high": data[-1].high,
            "low": data[-1].low,
            **compute_pattern_signals(data),
        }

    # Gap #15: ctx.risk.limits used to always be empty here, so RiskEngine
    # rejected every real decision with MISSING_LIMIT. Loads the ADMIN-approved
    # limits set via POST /risk-limits (see api/rest/risk_limits.py). If none
    # have ever been set, limits stays empty and MISSING_LIMIT is the correct,
    # intentional fail-closed behavior (a fresh deployment must not silently
    # approve trades against no real limit).
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

    # Faz 214: aynı Faz 206 düzeltmesi (proposed_size = sermaye bütçesi /
    # güncel fiyat) — bu ikinci giriş noktasında hiç uygulanmamıştı.
    current_price = (ctx.market.raw_snapshot or {}).get("close")
    if current_price:
        capital_per_trade = (
            risk_state["starting_capital"] * risk_state["max_capital_pct"]
            / max(risk_state["max_concurrent_positions"], 1)
        )
        ctx.decision.proposed_size = capital_per_trade / current_price

    result = engine.run(ctx)

    return {
        "cycle_id": str(result.cycle_id),
        "action": str(result.decision.action),
        "direction": result.decision.proposed_direction,
        "confidence": result.decision.confidence,
        "uncertainty": result.decision.uncertainty,
        "knowledge": result.cognition.relevant_knowledge,
        "risk_verdict": result.risk.evaluation.verdict,
        "risk_reasons": [r.code for r in result.risk.evaluation.reasons],
    }
