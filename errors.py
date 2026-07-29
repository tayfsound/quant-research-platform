"""
Domain exception hierarchy.
Tüm uygulama hataları buradan türer.
"""


class QuantPlatformError(Exception):
    """Tüm platform hatalarının base sınıfı."""
    def __init__(self, message: str = "Bir hata oluştu") -> None:
        self.message = message
        super().__init__(self.message)


# --- Market Data ---
class MarketDataError(QuantPlatformError):
    """Piyasa verisi hataları."""

class ExchangeConnectionError(MarketDataError):
    """Borsa bağlantı hatası."""

class InvalidSymbolError(MarketDataError):
    """Geçersiz sembol."""

class DataQualityError(MarketDataError):
    """Veri kalitesi hatası."""


# --- Simulation ---
class SimulationError(QuantPlatformError):
    """Simülasyon hataları."""

class OrderRejectedError(SimulationError):
    """Emir reddedildi."""

class InsufficientMarginError(SimulationError):
    """Yetersiz teminat."""

class LiquidationError(SimulationError):
    """Likidasyon hatası."""


# --- Risk ---
class RiskError(QuantPlatformError):
    """Risk yönetimi hataları."""

class RiskLimitExceededError(RiskError):
    """Risk limiti aşıldı."""

class CircuitBreakerTriggeredError(RiskError):
    """Devre kesici aktif."""


# --- ML ---
class MLError(QuantPlatformError):
    """Makine öğrenmesi hataları."""

class ModelNotFoundError(MLError):
    """Model bulunamadı."""

class TrainingFailedError(MLError):
    """Eğitim başarısız."""

class InferenceError(MLError):
    """Tahmin hatası."""


# --- Strategy ---
class StrategyError(QuantPlatformError):
    """Strateji hataları."""

class InvalidStrategyConfigError(StrategyError):
    """Geçersiz strateji konfigürasyonu."""


# --- Config ---
class ConfigError(QuantPlatformError):
    """Konfigürasyon hataları."""

class MissingConfigError(ConfigError):
    """Eksik konfigürasyon."""
