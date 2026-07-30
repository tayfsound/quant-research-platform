"""Eğitim pipeline'ı — ReplayMemory'den sample çekip model eğitir."""
from ml.training.replay_memory import ReplayMemory
from ml.training.feature_extractor import TrainingFeatureExtractor
from ml.models.classifier import DecisionClassifier
from typing import List, Dict, Any

class TrainingPipeline:
    def __init__(self, memory: ReplayMemory = None, classifier: DecisionClassifier = None):
        self.memory = memory or ReplayMemory(capacity=10000)
        self.classifier = classifier or DecisionClassifier()
        self.extractor = TrainingFeatureExtractor()
    
    def run(self, min_samples: int = 10) -> Dict[str, Any]:
        """Replay memory'den örnek çek, feature çıkar, model eğit."""
        if len(self.memory.memory) < min_samples:
            return {"status": "insufficient_data", "trained": False, "samples": len(self.memory.memory)}
        
        samples = self.memory.sample(batch_size=min(len(self.memory.memory), 1000))
        features = []
        labels = []
        
        for sample in samples:
            raw = sample.get("raw", {})
            outcome = raw.get("outcome", {})
            pnl = outcome.get("pnl", 0) if outcome else 0
            
            feat = self.extractor.extract_features(raw)
            features.append(feat)
            labels.append(1 if pnl > 0 else 0)
        
        if len(features) < min_samples:
            return {"status": "insufficient_features", "trained": False}
        
        self.classifier.train(features, labels)
        self.classifier.save()
        
        return {
            "status": "trained",
            "samples": len(features),
            "positive_ratio": sum(labels) / len(labels)
        }
