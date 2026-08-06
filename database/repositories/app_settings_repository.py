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
    # Faz 189: "stopsuz işlem yapmasın test modunda bile olsa" — aynı sembol
    # için art arda iki işlem açılışı arasında zorunlu minimum bekleme.
    "min_seconds_between_trades": "60",
    # Faz 190: dashboard'daki Start/Stop düğmesi. "false" iken AI yeni
    # pozisyon AÇMAZ ama mevcut açık pozisyonlar (PositionCloser) tamamen
    # bağımsız çalışmaya devam eder — hedefine ulaşan/vadesi dolan pozisyon
    # yine kapanır. Varsayılan "true" (önceki davranışla aynı, regresyon yok).
    "ai_enabled": "true",
    # Faz 194: AI'ın sürekli izlediği/işlem yapabildiği enstrümanlar —
    # kripto (Binance) + endeks/emtia/hisse (Yahoo Finance). Nasdaq/S&P500
    # ayrıca crypto sembollerine korelasyon sinyali olarak da besleniyor
    # (bkz. agents/technical_agent.py).
    # Faz 202: kullanıcı isteğiyle piyasa değeri/hacmi yüksek 3 kripto daha
    # eklendi (BNB, XRP, ADA — hepsi gerçek Binance USDT çiftleri).
    # PAXGUSDT/XAUTUSDT: gerçek altın-destekli kripto tokenlar (Binance'te
    # işlem görüyor, 24/7 — GC=F'nin CME saatleriyle sınırlı olmasının
    # tersine) — kullanıcı isteğiyle eklendi.
    "watchlist": "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,ADAUSDT,PAXGUSDT,XAUTUSDT,AAPL,NVDA,MSFT,GC=F,SI=F,^IXIC,^GSPC",
    # Faz 199: portfolio_fusion.py'nin gerçekten bağlanması — aynı cycle'da
    # birden fazla sembol eşzamanlı yönlü öneri üretirse, gerçek kovaryans
    # matrisiyle hesaplanan portföy VaR'ı bu yüzdeyi (sermayenin) aşarsa
    # önerilen büyüklükler orantılı olarak küçültülür.
    "max_portfolio_var_pct": "0.1",
    # Faz 204: MetaStage'in ACT/REDUCE/WAIT eşikleri — projenin ilk
    # commit'inden beri hiç değişmemiş, hiç gerekçelendirilmemiş
    # varsayılanlar (%70/%40). services/threshold_optimizer.py yeterli
    # gerçek kapalı işlem birikince (min. 20) bunları GERÇEK kâr/zarar
    # geçmişine göre kendi kendine güncelliyor; o zamana kadar bu
    # varsayılanlar kullanılıyor.
    "act_threshold": "0.7",
    "reduce_threshold": "0.4",
    # Faz 210: kullanıcı bulgusu — ilk gerçek kapanan iki işlem (PAXGUSDT,
    # XAUTUSDT) gerçekten take_profit hedefine ulaştı ama net PnL yine de
    # eksiye düştü, çünkü RiskTargetStage'in ATR-tabanlı hedefi (2x ATR)
    # bu fiyat seviyesinde (~4270) round-trip komisyona (~%0.1) kıyasla
    # çok küçüktü (%0.07). Bu, hedefin fiyatın en az bu yüzdesi kadar
    # olmasını zorunlu kılan bir alt sınır — komisyonu (%0.1) rahat
    # karşılayacak ama Faz 208'in "test modunda deneyim kazansın" amacını
    # (5% gibi çok yüksek bir eşik neredeyse hiçbir ATR-tabanlı işlemi
    # geçiremez) boğmayacak şekilde %0.5 varsayılan — kullanıcı Settings'ten
    # istediği gibi yükseltebilir/düşürebilir.
    "min_profit_target_pct": "0.005",
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
