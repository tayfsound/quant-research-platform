"""Training Intelligence Service — Eğitim verisi hazırlama ve kalite kontrol."""
import json
from pathlib import Path
from typing import Any

from contracts.decision_event import DecisionEvent
from ml.training.feature_extractor import TrainingFeatureExtractor
from ml.training.replay_memory import ReplayMemory
from contracts.decision_event import DecisionEvent

class TrainingIntelligence:
    def __init__(self, storage_path: str = "decision_logs", memory_capacity: int = 10000):
        self.storage_path = Path(storage_path)
        self.extractor = TrainingFeatureExtractor()
        self.quality_scorer = SampleQualityScorer()
        self.replay_memory = ReplayMemory(capacity=memory_capacity)

    def generate_training_data(self, output_path: str = "ml_training_dataset.jsonl", min_quality_score: float = 0.0) -> dict[str, Any]:
        """Karar geçmişlerinden zenginleştirilmiş ve kalite puanlı eğitim verisi üretir."""
        count = 0
        skipped_low_quality = 0
        samples = []

        # Ensure path is Path object
        search_path = Path(self.storage_path)
        files = list(search_path.glob("decision_*.json"))
        for filename in files:
            try:
                content = filename.read_text()
                event = DecisionEvent.model_validate_json(content)
                if not event.outcome:
                    print(f"DEBUG: Skipping {filename} - No outcome")
                    continue

                # Kalite puanını hesapla
                quality_metrics = self.quality_scorer.score_sample(event)
                quality_score = quality_metrics["final_quality_score"]

                if quality_score < min_quality_score:
                    skipped_low_quality += 1
                    continue

                features = self.extractor.extract_features(event)
                label_pnl = self.extractor.extract_label(event, "pnl")
                label_win = self.extractor.extract_label(event, "win")

                sample = {
                    "decision_id": str(event.id),
                    "timestamp": event.timestamp.isoformat(),
                    "features": features,
                    "label_pnl": label_pnl,
                    "label_win": label_win,
                    "quality_score": quality_score,
                    "quality_metrics": quality_metrics
                }
                samples.append(sample)
                count += 1
            except Exception:
                continue

        if samples:
            with open(output_path, "w") as f:
                for s in samples:
                    f.write(json.dumps(s) + "\n")
                    # Replay Memory'ye ekle
                    self.replay_memory.add({
                        "decision_id": s["decision_id"],
                        "features": s["features"],
                        "label": s["label_pnl"], # Varsayılan olarak PnL
                        "quality_score": s["quality_score"],
                        "timestamp": s["timestamp"]
                    })

        return {
            "sample_count": count,
            "skipped_low_quality": skipped_low_quality,
            "output_file": output_path,
            "feature_count": len(samples[0]["features"]) if samples else 0
        }

    def get_feature_stats(self, samples: list[dict]) -> dict:
        """Özelliklerin basit istatistiklerini hesaplar (kalite kontrol için)."""
        if not samples:
            return {}

        return {
            "total_samples": len(samples),
            "win_rate": sum(1 for s in samples if s["label_win"] == 1) / len(samples),
            "avg_quality_score": sum(s["quality_score"] for s in samples) / len(samples)
        }
