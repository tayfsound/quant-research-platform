"""Basit karar classifier'ı."""
import json
from pathlib import Path
from typing import List, Dict, Any
import pickle

class DecisionClassifier:
    def __init__(self, model_path: str = "models/decision_classifier.pkl"):
        self.model_path = Path(model_path)
        self.model = None
        self._trained = False
    
    def train(self, features: List[Dict[str, float]], labels: List[int]) -> None:
        """Feature dict listesinden eğitim."""
        from sklearn.ensemble import RandomForestClassifier
        import numpy as np
        
        X = np.array([[f.get(k, 0.0) for k in sorted(f.keys())] for f in features])
        y = np.array(labels)
        
        self.model = RandomForestClassifier(n_estimators=10, max_depth=5, random_state=42)
        self.model.fit(X, y)
        self._trained = True
        self._feature_keys = sorted(features[0].keys()) if features else []
    
    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        if not self._trained or self.model is None:
            return {"direction": 0, "confidence": 0.0}
        
        import numpy as np
        X = np.array([[features.get(k, 0.0) for k in self._feature_keys]])
        pred = self.model.predict(X)[0]
        proba = self.model.predict_proba(X)[0]
        confidence = max(proba)
        return {"direction": int(pred), "confidence": float(confidence)}
    
    def save(self) -> None:
        if self.model and self._trained:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.model_path, "wb") as f:
                pickle.dump({"model": self.model, "keys": self._feature_keys}, f)
    
    def load(self) -> bool:
        if not self.model_path.exists():
            return False
        with open(self.model_path, "rb") as f:
            data = pickle.load(f)
            self.model = data["model"]
            self._feature_keys = data["keys"]
            self._trained = True
        return True
