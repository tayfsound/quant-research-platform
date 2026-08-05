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
    timestamp: datetime = Field(default_factory=datetime.now)
