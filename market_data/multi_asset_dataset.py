"""Sprint 7: deterministic multi-asset OHLCV generation, spanning multiple
asset classes at once — same {symbol: [OHLCV,...]} shape used everywhere
else in this codebase, no new parallel data format.

Faz 268-sonrası düzeltme: docstring önceden "backtest/cognitive_backtest_
runner.py ve risk/limits/portfolio.py'ye besleniyor" diyordu — bu artık
doğru değil, hiçbiri bu modülü import etmiyor. Gerçek, TEK canlı tüketici:
tests/test_portfolio_fusion.py::test_three_plus_asset_classes_paper_
traded_with_portfolio_var_enforced (Faz 171 kapısı — 3+ varlık sınıfı aynı
anda, portföy VaR limiti gerçekten uygulanıyor mu). Canlı karar akışının
BİR PARÇASI DEĞİL, sadece o testin sentetik çok-varlık-sınıflı veri
ihtiyacı için var — market_data/asset_class.py'deki AssetClass/
SYMBOL_ASSET_CLASS de aynı şekilde sadece bu amaçla kullanılıyor (gerçek
watchlist sembolleriyle hiç çağrılmıyor, o yüzden az kapsamlı hardcoded
sözlüğü canlıda risk oluşturmuyor)."""
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
