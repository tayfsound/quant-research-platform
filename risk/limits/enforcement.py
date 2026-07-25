"""Risk limit uygulama motoru."""
from risk.limits.exposure import ExposureTracker
from risk.limits.schema import LimitType, RiskLimit


class RiskEvaluator:
    def __init__(self):
        self._limits: dict[LimitType, RiskLimit] = {}

    def load_limits(self, limits: list[RiskLimit]):
        for limit in limits:
            self._limits[limit.limit_type] = limit

    def evaluate(self, exposure: ExposureTracker, proposed_size: float, proposed_leverage: float) -> tuple[bool, str]:
        # Max position size
        if LimitType.MAX_POSITION_SIZE in self._limits:
            limit = self._limits[LimitType.MAX_POSITION_SIZE]
            if proposed_size > limit.value:
                return False, f"Position size {proposed_size} exceeds limit {limit.value}"

        # Max leverage
        if LimitType.MAX_LEVERAGE in self._limits:
            limit = self._limits[LimitType.MAX_LEVERAGE]
            if proposed_leverage > limit.value:
                return False, f"Leverage {proposed_leverage} exceeds limit {limit.value}"

        # Max exposure
        if LimitType.MAX_EXPOSURE in self._limits:
            limit = self._limits[LimitType.MAX_EXPOSURE]
            new_exposure = exposure.total_exposure + proposed_size
            if new_exposure > limit.value:
                return False, f"Total exposure {new_exposure} exceeds limit {limit.value}"

        # Max drawdown
        if LimitType.MAX_DRAWDOWN in self._limits:
            limit = self._limits[LimitType.MAX_DRAWDOWN]
            if exposure.current_drawdown >= limit.value:
                return False, f"Drawdown {exposure.current_drawdown:.2%} exceeds limit {limit.value:.2%}"

        # Max daily loss
        if LimitType.MAX_DAILY_LOSS in self._limits:
            limit = self._limits[LimitType.MAX_DAILY_LOSS]
            if abs(exposure.daily_loss) >= limit.value:
                return False, f"Daily loss {exposure.daily_loss} exceeds limit {limit.value}"

        return True, "approved"
