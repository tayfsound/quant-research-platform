"""Sprint 7: asset-class tagging. OHLCV/OHLCVProvider were already
asset-independent (no crypto-specific fields) — what was actually missing
was a way to group symbols by class for portfolio risk (Sprint 8) to
compute cross-asset correlation/VaR against."""
from enum import Enum


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    EQUITY_INDEX = "equity_index"
    COMMODITY = "commodity"
    FX = "fx"
    BOND = "bond"


# Deliberately a plain dict, not a DB table: this is static reference data
# (what kind of thing a symbol is), not something that changes at runtime.
SYMBOL_ASSET_CLASS: dict[str, AssetClass] = {
    "BTCUSDT": AssetClass.CRYPTO,
    "ETHUSDT": AssetClass.CRYPTO,
    "SOLUSDT": AssetClass.CRYPTO,
    "XAUUSD": AssetClass.COMMODITY,
    "NASDAQ": AssetClass.EQUITY_INDEX,
    "DXY": AssetClass.FX,
    "US10Y": AssetClass.BOND,
}


def asset_class_of(symbol: str) -> AssetClass:
    if symbol not in SYMBOL_ASSET_CLASS:
        raise ValueError(f"unknown symbol, not registered in SYMBOL_ASSET_CLASS: {symbol}")
    return SYMBOL_ASSET_CLASS[symbol]
