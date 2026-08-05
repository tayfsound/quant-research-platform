"""Faz 188: uygulama ayarları (trading_mode, risk limitleri vb.) — tek
key-value kaynağı. risk_limits (faz172) tablosundan kasıtlı olarak ayrı:
o hash-imzalı, sayısal risk eşikleri için (max_position_size, max_drawdown);
bu, daha genel operasyonel ayarlar için (mod anahtarı gibi string değerler
de içeriyor)."""
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, String
from sqlalchemy.orm import Session

from database.base import Base

DEFAULTS: dict[str, str] = {
    "trading_mode": "test",
    "max_concurrent_positions": "3",
    "max_capital_pct": "0.5",
    "starting_capital": "10000",
    "trade_horizon": "short",
}

# Faz 187'nin PositionCloser.hold_seconds'ına karşılık gelen ön tanımlı
# vadeler — "kısa vadeli işlemler alsın, bakiyeyi kilitlemesin" isteğinin
# doğrudan karşılığı.
TRADE_HORIZON_SECONDS: dict[str, int] = {
    "short": 600,       # 10 dakika
    "medium": 14400,    # 4 saat
    "long": 86400,      # 1 gün
}


class AppSettingModel(Base):
    __tablename__ = "app_settings"
    key = Column(String(64), primary_key=True)
    value = Column(String(256), nullable=False)
    updated_by = Column(String(128), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class AppSettingsRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, key: str) -> str:
        row = self.session.query(AppSettingModel).filter_by(key=key).first()
        if row is not None:
            return row.value
        return DEFAULTS.get(key, "")

    def get_all(self) -> dict[str, str]:
        rows = {r.key: r.value for r in self.session.query(AppSettingModel).all()}
        return {**DEFAULTS, **rows}

    def set(self, key: str, value: str, updated_by: str) -> None:
        row = self.session.query(AppSettingModel).filter_by(key=key).first()
        now = datetime.now(UTC)
        if row is None:
            row = AppSettingModel(key=key, value=value, updated_by=updated_by, updated_at=now)
            self.session.add(row)
        else:
            row.value = value
            row.updated_by = updated_by
            row.updated_at = now
        self.session.commit()
