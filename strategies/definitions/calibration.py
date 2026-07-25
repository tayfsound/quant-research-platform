"""Ajan güven kalibrasyonu."""

class ConfidenceCalibrator:
    def __init__(self):
        self._history: list[tuple[float, bool]] = []  # (confidence, was_correct)

    def record(self, confidence: float, was_correct: bool):
        self._history.append((confidence, was_correct))

    def calibrate(self, raw_confidence: float) -> float:
        if len(self._history) < 10:
            return raw_confidence
        correct_rate = sum(1 for _, c in self._history[-50:] if c) / min(len(self._history), 50)
        return raw_confidence * (0.5 + 0.5 * correct_rate)
