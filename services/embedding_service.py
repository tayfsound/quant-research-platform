"""Embedding Service — thread‑safe singleton, normalize edilmiş vektörler."""
from threading import Lock

from sentence_transformers import SentenceTransformer

_model = None
_model_lock = Lock()

def get_embedding_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model

class EmbeddingService:
    def __init__(self):
        self.model = get_embedding_model()

    def encode_episode(self, episode: dict) -> list[float]:
        text = self._episode_to_text(episode)
        return self.model.encode(text, normalize_embeddings=True).tolist()

    def encode_features(self, features: dict[str, float], symbol: str = "") -> list[float]:
        text = f"Symbol:{symbol} " + " ".join(f"{k}={v}" for k, v in features.items())
        return self.model.encode(text, normalize_embeddings=True).tolist()

    def _episode_to_text(self, episode: dict) -> str:
        text = f"Symbol:{episode.get('symbol','')} Decision:{episode.get('decision','')} Expression:{episode.get('binding_expression','')} "
        obs = episode.get("observation", {})
        if isinstance(obs, dict):
            features = obs.get("features", {})
            text += " ".join(f"{k}={v}" for k, v in features.items())
        return text
