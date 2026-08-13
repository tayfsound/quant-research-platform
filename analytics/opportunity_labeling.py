"""Labeling ve Gerçek Fırsat Dataset'i — Faz 444-468 (Cognitive Core 2.0).

AI'nin ALDIĞI işlemlerin MAE/MFE'si zaten ölçülüyor (analytics/mae_mfe.py::
compute_mae_mfe). AMA reddettiği (decisions.status='no_trade', direction
IN LONG/SHORT — DB'de 622 LONG + 437 SHORT gerçek yönlü-ama-reddedilmiş
karar doğrulandı, bkz. analytics/mae_mfe.py::compute_selection_bias_
correction'ın docstring'i) fırsatların GERÇEKTE ne olduğu hiç
etiketlenmiyordu — compute_selection_bias_correction bunu GİRDİ olarak
bekliyordu ama üretecek bir mekanizma yoktu.

Bu modül GERÇEK geçmiş bar verisiyle (kararın verildiği ANDAN itibaren,
Binance) o reddedilen fırsatın hipotetik giriş fiyatını ve MAE/MFE'sini
hesaplıyor — compute_mae_mfe ile AYNI, zaten doğrulanmış mantığı
kullanıyor, yeni bir hesaplama icat etmiyor. Binance'te olmayan semboller
(GC=F/SI=F gibi) ya da yetersiz veri için fail-closed None döner."""
from datetime import datetime

from analytics.mae_mfe import compute_mae_mfe
from exchange_gateway.binance.adapter import BinanceAdapter
from market_data.ingestion.ohlcv import from_binance_klines

DEFAULT_MAX_FORWARD_BARS = 100


async def label_rejected_opportunity(
    symbol: str,
    direction: str,
    decision_timestamp: datetime,
    timeframe: str = "15m",
    max_forward_bars: int = DEFAULT_MAX_FORWARD_BARS,
) -> dict | None:
    """decision_timestamp: kararın GERÇEKTEN verildiği an — bar geçmişi
    bu andan İTİBAREN (since=decision_timestamp) çekiliyor, ilk bar'ın
    kapanışı hipotetik giriş fiyatı olarak kullanılıyor."""
    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        raw = await adapter.fetch_ohlcv(symbol, timeframe, since=decision_timestamp, limit=max_forward_bars)
    except Exception:
        return None
    finally:
        await adapter.disconnect()

    bars = from_binance_klines(raw)
    if len(bars) < 2:
        return None

    entry_price = bars[0].close
    label = compute_mae_mfe(direction, entry_price, bars)
    if label["mae_pct"] is None:
        return None

    return {
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry_price,
        **label,
    }
