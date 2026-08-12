"""Order Flow Domain Contracts — mikroyapı sinyalleri."""
from datetime import datetime

from pydantic import BaseModel, Field


class OrderFlowContext(BaseModel):
    """OrderFlowAgent için mikroyapı bağlamı — gerçek order book verisiyle
    besleniyor (database/repositories/market_data_repository.py::
    get_latest_order_book_snapshot, Faz 186)."""
    bid_ask_imbalance: float = 0.0   # -1..1, pozitif = bid tarafı ağır basıyor
    spread_bps: float = 0.0          # Baz puan cinsinden bid-ask spread
    aggressive_buy_ratio: float = 0.5  # 0..1, son trade'lerin ne kadarı agresif alış (taker buy)
    # Faz 247-249: vadeli işlem verisi — exchange_gateway/binance/adapter.py::
    # fetch_funding_rate/fetch_open_interest (gerçek Binance Futures API,
    # önceden yanlış temel URL'e gidip hiç çalışmıyordu). Vadeli kontratı
    # olmayan bir sembolde (fail-closed) None/"unknown" kalır.
    funding_rate: float | None = None  # 8 saatlik oran; pozitif = long'lar short'lara ödüyor
    open_interest_trend: str = "unknown"  # "rising" | "falling" | "stable" | "unknown"
    timestamp: datetime = Field(default_factory=datetime.now)
