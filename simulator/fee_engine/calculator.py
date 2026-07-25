"""Komisyon hesaplama motoru."""
from dataclasses import dataclass


@dataclass
class FeeSchedule:
    maker_fee: float = 0.0002   # %0.02
    taker_fee: float = 0.0004   # %0.04

class FeeEngine:
    def __init__(self, schedule: FeeSchedule | None = None):
        self.schedule = schedule or FeeSchedule()

    def calculate(self, notional: float, is_maker: bool = False) -> float:
        rate = self.schedule.maker_fee if is_maker else self.schedule.taker_fee
        return notional * rate
