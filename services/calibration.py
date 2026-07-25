"""Calibration Metrics — Brier Score, ECE, Reliability Diagram, Confidence Histogram."""
from collections import defaultdict

class CalibrationMetrics:
    def __init__(self):
        self.predictions: list[tuple[float, bool]] = []  # (confidence, was_correct)

    def record(self, confidence: float, was_correct: bool):
        self.predictions.append((confidence, was_correct))

    def brier_score(self) -> float:
        if not self.predictions:
            return 0.0
        total = sum((conf - int(correct)) ** 2 for conf, correct in self.predictions)
        return total / len(self.predictions)

    def expected_calibration_error(self, n_bins: int = 10) -> float:
        if not self.predictions:
            return 0.0
        bin_size = 1.0 / n_bins
        bins = defaultdict(list)
        for conf, correct in self.predictions:
            bin_idx = min(int(conf / bin_size), n_bins - 1)
            bins[bin_idx].append((conf, correct))
        ece = 0.0
        for bin_idx in range(n_bins):
            if bins[bin_idx]:
                avg_conf = sum(c for c, _ in bins[bin_idx]) / len(bins[bin_idx])
                accuracy = sum(1 for _, correct in bins[bin_idx] if correct) / len(bins[bin_idx])
                ece += (len(bins[bin_idx]) / len(self.predictions)) * abs(avg_conf - accuracy)
        return ece

    def reliability_diagram(self, n_bins: int = 10) -> list[dict]:
        """Güvenilirlik diyagramı — boş binler de dahil."""
        bin_size = 1.0 / n_bins
        bins = defaultdict(list)
        for conf, correct in self.predictions:
            bin_idx = min(int(conf / bin_size), n_bins - 1)
            bins[bin_idx].append((conf, correct))
        result = []
        for bin_idx in range(n_bins):
            if bins[bin_idx]:
                avg_conf = sum(c for c, _ in bins[bin_idx]) / len(bins[bin_idx])
                accuracy = sum(1 for _, correct in bins[bin_idx] if correct) / len(bins[bin_idx])
                result.append({
                    "bin": bin_idx,
                    "range": f"{bin_idx * bin_size:.1f}-{(bin_idx + 1) * bin_size:.1f}",
                    "avg_confidence": round(avg_conf, 3),
                    "accuracy": round(accuracy, 3),
                    "count": len(bins[bin_idx]),
                })
            else:
                result.append({
                    "bin": bin_idx,
                    "range": f"{bin_idx * bin_size:.1f}-{(bin_idx + 1) * bin_size:.1f}",
                    "avg_confidence": 0.0,
                    "accuracy": None,
                    "count": 0,
                })
        return result

    def confidence_histogram(self, n_bins: int = 10) -> list[dict]:
        """Güven histogramı — sistem hangi güven aralığında ne sıklıkla tahmin yapıyor?"""
        bin_size = 1.0 / n_bins
        bins = defaultdict(int)
        for conf, _ in self.predictions:
            bin_idx = min(int(conf / bin_size), n_bins - 1)
            bins[bin_idx] += 1
        total = len(self.predictions)
        return [
            {
                "bin": i,
                "range": f"{i * bin_size:.1f}-{(i + 1) * bin_size:.1f}",
                "count": bins[i],
                "percentage": round(bins[i] / total * 100, 1) if total > 0 else 0.0,
            }
            for i in range(n_bins)
        ]
