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
    # Faz 412 — kullanıcı isteği: order_flow domain'inin bullish_low
    # rejiminde zararlı olduğu (ablation: -193$/işlem beklenti; yönlü IC:
    # p=0.014) bulundu — pattern_agent.py'deki AYNI market_regime deseni.
    market_regime: str = "unknown"
    # Faz 464 (2026-09-09) — Faz 436'nin fiyat/OI/funding UCLUSUNU tek bir
    # kategoriye ayiran sinyali. Bir yil once "once gozlemle, kanitlanirsa
    # wire et" diye eklenmis, `ctx.market.features`'ta akmis ama HIC
    # olculmemisti. Faz 462/463'te olculdu ve dort kanit sartini birden
    # gecen TEK YENI ozellik oldu (bkz. agents/order_flow_agent.py).
    # Veri yoksa None -- uydurma bir kategori asla uretilmiyor.
    order_flow_relationship_category: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
