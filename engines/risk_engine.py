"""Risk Engine – tüm ret sebeplerini biriktirir, tek otorite."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.risk import RiskReason
from observability.metrics import risk_decisions_total, risk_rejections_total


class RiskEngine:
    def __init__(self, secret: str = ""):
        self.secret = secret

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        limits = ctx.risk.limits
        proposed = ctx.decision.proposed_size
        reasons: list[RiskReason] = []
        symbol = ctx.market.symbol or "unknown"

        # 1. Limit var mı?
        max_size_limit = limits.get("max_position_size")
        if max_size_limit is None:
            ctx.risk.evaluation.verdict = "rejected"
            ctx.risk.evaluation.reasons = [
                RiskReason(code="MISSING_LIMIT", message="No max_position_size limit defined", severity="critical")
            ]
            risk_decisions_total.labels(verdict="rejected", symbol=symbol).inc()
            risk_rejections_total.labels(reason="MISSING_LIMIT").inc()
            return ctx

        # 2. Hash doğru mu?
        if not max_size_limit.verify(self.secret):
            reasons.append(RiskReason(code="HASH_MISMATCH", message="Risk limit hash verification failed", severity="critical"))

        # 3. Pozisyon limiti aşıldı mı?
        if proposed > max_size_limit.value:
            reasons.append(RiskReason(code="SIZE_EXCEEDED", message=f"Size {proposed} > limit {max_size_limit.value}", severity="warning"))

        # 4. Drawdown limiti aşıldı mı?
        max_drawdown_limit = limits.get("max_drawdown")
        if max_drawdown_limit and ctx.risk.current_drawdown >= max_drawdown_limit.value:
            reasons.append(RiskReason(code="MAX_DRAWDOWN", message=f"Drawdown {ctx.risk.current_drawdown:.1%} >= {max_drawdown_limit.value:.1%}", severity="critical"))

        if reasons:
            ctx.risk.evaluation.verdict = "rejected"
            ctx.risk.evaluation.reasons = reasons
            risk_decisions_total.labels(verdict="rejected", symbol=symbol).inc()
            for r in reasons:
                risk_rejections_total.labels(reason=r.code).inc()
            return ctx

        # Onay
        factor = max(0.5, min(ctx.risk.adjustment.factor, 1.0))
        ctx.risk.evaluation.verdict = "approved"
        ctx.decision.risk_adjusted_size = proposed * factor
        risk_decisions_total.labels(verdict="approved", symbol=symbol).inc()
        return ctx
