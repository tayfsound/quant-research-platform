"""Funding fee hesaplama."""
from datetime import datetime


class FundingRateAccrual:
    def __init__(self):
        self._last_payment: datetime | None = None
        self._current_rate: float = 0.0

    def update_rate(self, rate: float):
        self._current_rate = rate

    def calculate_payment(self, position_size: float, timestamp: datetime) -> float:
        if self._last_payment is None:
            self._last_payment = timestamp
            return 0.0
        hours = (timestamp - self._last_payment).total_seconds() / 3600
        if hours >= 8:  # Genelde 8 saatte bir
            payment = position_size * self._current_rate
            self._last_payment = timestamp
            return payment
        return 0.0
