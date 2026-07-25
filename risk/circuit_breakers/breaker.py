"""Circuit breaker ve acil durum durdurma."""
from datetime import datetime, timedelta
from enum import StrEnum


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = BreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time: datetime | None = None

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        if self.failure_count >= self.failure_threshold:
            self.state = BreakerState.OPEN

    def record_success(self):
        if self.state == BreakerState.HALF_OPEN:
            self.state = BreakerState.CLOSED
            self.failure_count = 0

    def allow_request(self) -> bool:
        if self.state == BreakerState.CLOSED:
            return True
        if self.state == BreakerState.OPEN:
            if self.last_failure_time and \
               datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout):
                self.state = BreakerState.HALF_OPEN
                return True
            return False
        return True

class EmergencyStop:
    def __init__(self):
        self._active = False

    def trigger(self, reason: str):
        self._active = True
        return f"EMERGENCY STOP: {reason}"

    def release(self):
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active
