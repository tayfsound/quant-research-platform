from fastapi import APIRouter, Depends

from config import get_settings
from contracts.auth import Role
from contracts.context import CognitiveCycleContext
from database.repositories.risk_limit_repository import load_active_limits
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
    ctx = CognitiveCycleContext()
    ctx.market.symbol = symbol
    ctx.market.timeframe = settings.DEFAULT_TIMEFRAME
    data = get_ohlcv_provider().get_ohlcv(symbol, settings.DEFAULT_TIMEFRAME, limit=100)
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
