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
                # Faz 241: kritik bulgu — macOS'ta MPS (Metal GPU) cihazı
                # otomatik seçiliyordu; bu makinenin Metal compiler servisi
                # (MTLCompilerService) arka planda çöktüğünde (uyku/uyanma
                # döngüsü, ya da başka bir işlemin GPU'yu paylaşması gibi
                # sebeplerle) HER TEK trading cycle çağrısı bu embed adımında
                # exception fırlatıp cognitive_engine'i çökertiyordu — sistem
                # saatlerce hiç karar üretemedi ama hiçbir hata görünür
                # şekilde loglanmadı (celery worker log'una gömülü kaldı,
                # /health/signals doğru "unhealthy" diyordu ama kimse
                # bakmadıkça fark edilmiyordu). Model çok küçük (384-dim,
                # tek string) — CPU'da da milisaniyeler içinde çalışıyor,
                # 120s'lik cycle döngüsü için performans farkı önemsiz.
                # MPS'e güvenmek yerine sabit CPU kullanmak bu çökme
                # sınıfını tamamen ortadan kaldırıyor.
                _model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
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
