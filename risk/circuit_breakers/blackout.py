"""Blackout filtreleri — haber, volatilite, likidite."""
from datetime import datetime, timedelta


class BlackoutFilter:
    def __init__(self):
        self._blackout_until: datetime | None = None

    def trigger(self, reason: str, duration_minutes: int = 30):
        self._blackout_until = datetime.now() + timedelta(minutes=duration_minutes)

    def is_active(self) -> bool:
        if self._blackout_until is None:
            return False
        return datetime.now() < self._blackout_until

    def release(self):
        self._blackout_until = None
