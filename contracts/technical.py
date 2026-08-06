"""Technical Analysis Domain Contracts."""
from datetime import datetime

from pydantic import BaseModel, Field


class TechnicalContext(BaseModel):
    """TechnicalAgent için yapısal teknik analiz bağlamı."""
    trend: str = "neutral"              # "bullish", "bearish", "neutral"
    momentum: str = "neutral"           # "strengthening", "weakening", "neutral"
    market_structure: str = "neutral"   # "higher_highs", "lower_lows", "ranging"
    volume_confirmation: bool = False   # Hacim trendi destekliyor mu?
    rsi_value: float = 50.0
    ema_alignment: str = "neutral"      # "bullish_aligned", "bearish_aligned", "mixed"
    volatility_regime: str = "normal"   # "low", "normal", "high"
    key_levels: list[float] = Field(default_factory=list)  # Kritik destek/direnç seviyeleri
    timestamp: datetime = Field(default_factory=datetime.now)
    # Faz 193: TradingView webhook alarmı — ikinci görüş, hiçbir zaman
    # ajanın kendi hesapladığı yönü tek başına belirlemiyor/ezmiyor.
    # "bullish"/"bearish"/None (yakın zamanda alarm yoksa ya da
    # tanınmayan bir format geldiyse).
    external_signal: str | None = None
    external_signal_source: str | None = None
    # Faz 194: Nasdaq + S&P500'ün GERÇEKTEN ikisi de aynı yönde ise (ikisi
    # de bullish ya da ikisi de bearish) — kripto, geleneksel risk-varlığı
    # piyasalarıyla korele gidiyor. Sadece kripto sembolleri için doldurulur;
    # ikisi anlaşmazsa ya da henüz analiz edilmemişlerse None (icat edilmiş
    # bir "hafif korelasyon" sinyali değil, ya net bir uyum ya da hiç sinyal).
    correlated_market_trend: str | None = None
    # Faz 237: kullanıcı isteği — ek matematiksel TA yöntemleri. Dördü de
    # kesin tanımlı, standart formüller (bkz. market_data/features/
    # signal_engine.py).
    bollinger_percent_b: float = 0.5   # 0=alt bant, 1=üst bant (aralık dışına çıkabilir)
    bollinger_bandwidth: float = 0.0   # bantların SMA'ya göre göreli genişliği (düşük=sıkışma)
    vwap_deviation_pct: float = 0.0    # fiyatın VWAP'a göre göreli sapması
    adx: float = 0.0                   # trend GÜCÜ (>25 güçlü, <20 zayıf/yatay — standart eşikler)
    di_plus: float = 0.0
    di_minus: float = 0.0
    obv_trend: str = "flat"            # "rising", "falling", "flat"
    price_obv_divergence: str = "none"  # "bullish_divergence", "bearish_divergence", "none"
