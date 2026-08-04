"""Sprint 7: deterministic multi-asset OHLCV generation, spanning multiple
asset classes at once. Feeds directly into backtest/cognitive_backtest_runner.py
and risk/limits/portfolio.py — same {symbol: [OHLCV,...]} shape used
everywhere else in this codebase, no new parallel data format."""
from market_data.asset_class import AssetClass, asset_class_of
from market_data.ingestion.mock_adapter import MockOHLCVAdapter
from market_data.ingestion.ohlcv import OHLCV


def generate_multi_asset_dataset(
    symbols: list[str],
    bars: int = 200,
    seed: int = 42,
    base_price: float = 100.0,
) -> dict[str, list[OHLCV]]:
    """One deterministic MockOHLCVAdapter per symbol, seeded off the base
    seed + symbol so results are reproducible but not identical across
    symbols (a real backtest with every symbol moving in lockstep would be
    meaningless for portfolio/correlation testing)."""
    data = {}
    for i, symbol in enumerate(symbols):
        adapter = MockOHLCVAdapter(seed=seed + i, base_price=base_price)
        data[symbol] = adapter.generate(bars)
    return data


def asset_classes_represented(symbols: list[str]) -> set[AssetClass]:
    return {asset_class_of(s) for s in symbols}
