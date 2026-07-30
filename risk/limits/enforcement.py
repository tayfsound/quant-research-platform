"""Risk limit enforcement."""
from dataclasses import dataclass
from typing import Optional

@dataclass
class RiskLimit:
    max_position_size: float = 1.0
    max_drawdown_pct: float = 0.05
    daily_loss_limit: float = 1000.0
    signed_hash: Optional[str] = None

class RiskEnforcer:
    def __init__(self, limit: RiskLimit = None):
        self.limit = limit or RiskLimit()
        self.daily_pnl: float = 0.0
        self.peak_equity: float = 10000.0
    
    def check_position(self, size: float, current_equity: float) -> tuple[bool, str]:
        if size > self.limit.max_position_size:
            return False, "POSITION_SIZE_EXCEEDED"
        drawdown = (self.peak_equity - current_equity) / self.peak_equity
        if drawdown > self.limit.max_drawdown_pct:
            return False, "DRAWDOWN_LIMIT"
        return True, "OK"
    
    def check_daily_loss(self, pnl: float) -> tuple[bool, str]:
        self.daily_pnl += pnl
        if self.daily_pnl < -self.limit.daily_loss_limit:
            return False, "DAILY_LOSS_LIMIT"
        return True, "OK"
    
    def update_equity(self, equity: float):
        if equity > self.peak_equity:
            self.peak_equity = equity
