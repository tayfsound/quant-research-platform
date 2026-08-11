"""Merkezi ayar sinifi."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG"
    API_PORT: int = 8000
    DASHBOARD_PORT: int = 5173

    DATABASE_URL: str = "postgresql+asyncpg://quant:quantpass@localhost:5432/quantdb"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://quant:quantpass@localhost:5432/quantdb"
    TIMESCALE_URL: str = "postgresql+asyncpg://quant:quantpass@localhost:5432/quantdb"

    REDIS_URL: str = "redis://localhost:6379/0"

    PGVECTOR_EMBEDDING_DIM: int = 384

    SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    # Faz 268ag — kullanıcı isteği: "30 gün olsun." Önceki 1440dk (24 saat),
    # bu proje günler süren tek oturumlarla çalıştığı için token'ın sık sık
    # sona ermesine yol açıyordu.
    JWT_EXPIRE_MINUTES: int = 43200
    # Güvenlik incelemesi bulgusu (güven 5/10): boşsa ilk /auth/register
    # çağrısı otomatik ADMIN olur (dev/local kolaylığı, geriye dönük uyumlu).
    # Prod'da set edilirse, o ilk-admin bootstrap'ı bu token'ı bilmeyen biri
    # yapamaz — TOCTOU'yu kapatmaz ama saldırı yüzeyini "token'ı bilen"e indirir.
    ADMIN_SETUP_TOKEN: str = ""

    RISK_SIGNING_KEY_PATH: Path = Path("./keys/risk_private.pem")

    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    BYBIT_API_KEY: str = ""
    BYBIT_API_SECRET: str = ""
    OKX_API_KEY: str = ""
    OKX_API_SECRET: str = ""
    COINBASE_API_KEY: str = ""
    COINBASE_API_SECRET: str = ""
    KRAKEN_API_KEY: str = ""
    KRAKEN_API_SECRET: str = ""

    MARKET_DATA_SOURCE: Literal["mock", "binance"] = "mock"
    BINANCE_BASE_URL: str = "https://api.binance.com"
    DEFAULT_SYMBOL: str = "BTCUSDT"
    DEFAULT_TIMEFRAME: str = "1m"
    # Faz 239: KRİTİK bulgu — canlı üretimde doğrulandı. Gerçek Binance
    # isteği HERHANGİ bir sebeple başarısız olursa (rate limit, ağ hatası,
    # asyncio nested-loop hatası vb.), True iken BinanceProvider sessizce
    # MockOHLCVAdapter'a (varsayılan base_price=$50,000, SEMBOLDEN
    # BAĞIMSIZ) düşüyordu. services/position_closer.py bu sahte fiyatı
    # gerçek stop/target seviyeleriyle karşılaştırıp hayali kapanışlar
    # üretti — gerçek örnek: ADAUSDT pozisyonu ($0.20 gerçek fiyat),
    # exit_price=$49,855 (BTC ölçeğinde mock fallback) ile "take_profit"a
    # ulaştı sanılıp $9.9 MİLYON hayali kâr kaydetti. Bu sadece PnL
    # gösterimini değil, position_closer.py::_record_agent_learning() ve
    # WeightOptimizer üzerinden AJAN ÖĞRENME SİNYALİNİ de kirletti.
    # False'a çekildi: gerçek veri yoksa PositionCloser/CognitiveOrchestrator
    # zaten "if not data: continue/return None" ile o cycle'ı/pozisyonu
    # dürüstçe atlıyor — sahte veriyle gerçek finansal karar/kapanış asla
    # daha iyi değil, ondan HER ZAMAN kötü. Aynı fail-closed/fail-fake-değil
    # ilkesi projenin geri kalanında (onchain/sentiment/macro) zaten
    # uygulanıyordu, burada uygulanmıyordu.
    MARKET_DATA_FALLBACK_TO_MOCK: bool = False

    # Faz 196: on-chain metrik motoru — sadece gerçekten kolay/dürüst
    # ölçülebilen metrikler (bkz. market_data/onchain/onchain_provider.py).
    INFURA_API_KEY: str = ""
    INFURA_MAINNET_URL: str = ""
    ALCHEMY_API_KEY: str = ""
    HELIUS_API_KEY: str = ""
    # Faz 197: MacroAgent'a gerçek FRED verisi.
    FRED_API_KEY: str = ""
    # Faz 230: kullanıcı isteği — sosyal medya sentiment. Reddit'in genel
    # kimliksiz JSON API'si artık 403 döndürüyor (doğrulandı) — gerçek
    # veri için ücretsiz bir "script" tipi Reddit uygulaması kaydı
    # gerekiyor (reddit.com/prefs/apps, key gerektirmez, tamamen ücretsiz).
    # Boşsa (kayıt yapılmadıysa) sentiment sağlayıcı None döner — fail-closed,
    # fail-fake değil, aynı FRED_API_KEY/HELIUS_API_KEY konvansiyonu.
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""

    # TradingView webhook'ları custom auth header göndermiyor (Pine Script
    # alert mekanizması bunu desteklemiyor) — paylaşılan bir secret'ı alert
    # mesajının JSON gövdesine gömüp burada doğruluyoruz. Boşsa (dev modu)
    # doğrulama atlanır — aynı SECRET_KEY/ADMIN_SETUP_TOKEN konvansiyonu.
    TRADINGVIEW_WEBHOOK_SECRET: str = ""

@lru_cache
def get_settings() -> Settings:
    return Settings()
