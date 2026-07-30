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
    JWT_EXPIRE_MINUTES: int = 1440

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
    MARKET_DATA_FALLBACK_TO_MOCK: bool = True

@lru_cache
def get_settings() -> Settings:
    return Settings()
