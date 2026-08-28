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
                #
                # Faz 368 — ikinci, farklı bir çökme sınıfı: gerçek olay
                # ("RuntimeError: Cannot send a request, as the client has
                # been closed"), ~50 dakikada 3 kez, her seferinde bir
                # trading cycle'ın (~50 sembol) TAMAMI kayboluyordu. Kök
                # neden: model dosyaları makinede ZATEN tam olarak
                # önbelleklenmiş (~/.cache/huggingface/hub) ama varsayılan
                # davranış her yüklemede yine de HuggingFace Hub'a
                # "güncelleme var mı" diye bir ağ isteği atıyordu — bu
                # gereksiz ağ bağımlılığı, huggingface_hub'ın kendi HTTP
                # istemcisinde arada bir görülen bir yarış durumuyla
                # ("client has been closed") birleşince tüm cycle'ı
                # çökertiyordu. local_files_only=True ile önbellek varsa
                # hiç ağa DOKUNULMUYOR — bu çökme sınıfı tamamen ortadan
                # kalkıyor, üstelik yükleme de hızlanıyor (ağ round-trip'i
                # yok). Önbellek YOKSA (ör. taze bir deploy) fail-closed
                # DEĞİL — normal (ağ destekli) yüklemeye düşülüyor, ilk
                # kurulumda hâlâ çalışır.
                try:
                    _model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu", local_files_only=True)
                except Exception:
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
