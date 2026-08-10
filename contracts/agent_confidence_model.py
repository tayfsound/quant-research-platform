"""Faz 264: kullanıcı isteği — ajan içi özellik ağırlıklarının (RSI/trend/
momentum vb.) elle yazılmış sabitler yerine gerçek sonuçlardan öğrenilmesi.
Kayan pencereli, periyodik olarak yeniden eğitilen bir lojistik regresyon
modelinin, bir ajanın kendi çağrısının doğru çıkma olasılığını tahmin edip
o ajanın confidence'ını (agent'ın kendi yön/skor mantığını DEĞİŞTİRMEDEN,
sadece ne kadar güvenilmesi gerektiğini) ayarlamasını sağlıyor."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentConfidenceModel(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    domain: str
    trained_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    window_size: int
    sample_count: int
    numeric_features: list[str] = Field(default_factory=list)
    boolean_features: list[str] = Field(default_factory=list)
    # feature adı -> eğitimde görülen kategorik değerler (one-hot kolon sırasını belirler)
    categorical_features: dict[str, list[str]] = Field(default_factory=dict)
    scaler_mean: list[float] = Field(default_factory=list)
    scaler_scale: list[float] = Field(default_factory=list)
    coefficients: list[float] = Field(default_factory=list)
    intercept: float = 0.0
    # Eğitim verisindeki gerçek "doğru çıktı" oranı — çarpanı normalize
    # etmek için (P(doğru)/taban_oranı) kullanılıyor, mutlak P(doğru) değil.
    baseline_correctness_rate: float = 0.5
    train_accuracy: float = 0.0
    test_accuracy: float = 0.0
    test_auc: float | None = None
