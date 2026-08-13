"""Liquidity-Adjusted VaR (LVaR) — Bangia, Diebold, Schuermann, Stroughair
(1999) yöntemi. Standart parametrik VaR (risk/limits/portfolio.py) SADECE
fiyat riskini ölçüyor — pozisyonu gerçekten kapatırken bid-ask spread'in
ne kadar ek maliyete yol açacağını hesaba katmıyor. Az likit bir sembolde
(geniş/değişken spread) gerçek çıkış maliyeti fiyat VaR'ının çok üzerinde
olabilir.

LVaR = Price VaR + Liquidity Cost
Liquidity Cost = 0.5 * position_value * (mean_spread_pct + z_score * std_spread_pct)

Kasıtlı olarak SADECE ölçüm/rapor — risk/limits/portfolio.py'nin GERÇEKTEN
uygulanan VaR limitini burada DEĞİŞTİRMİYOR (o dosya AI/learning kodunun
import edip çıktısını değiştiremeyeceği korumalı bir katman — bkz. o
dosyanın kendi docstring'i)."""
import numpy as np

MIN_SPREAD_SAMPLE_SIZE = 10
DEFAULT_Z_SCORE = 1.645  # tek-taraflı %95 normal kuantili — portfolio.py ile AYNI varsayım


def compute_liquidity_cost(
    spread_bps_series: list[float],
    position_value: float,
    z_score: float = DEFAULT_Z_SCORE,
) -> dict | None:
    """spread_bps_series: GERÇEK geçmiş bid-ask spread (baz puan) ölçümleri
    — market_data_repository.py'nin order_book_snapshots tablosundan.
    MIN_SPREAD_SAMPLE_SIZE altında fail-closed None döner (icat edilmiş
    bir likidite maliyeti asla üretilmez)."""
    if len(spread_bps_series) < MIN_SPREAD_SAMPLE_SIZE:
        return None

    spread_pct = np.array(spread_bps_series) / 10000.0  # bps -> oran
    mean_spread = float(np.mean(spread_pct))
    std_spread = float(np.std(spread_pct))

    liquidity_cost = 0.5 * position_value * (mean_spread + z_score * std_spread)
    return {
        "mean_spread_bps": round(mean_spread * 10000, 4),
        "std_spread_bps": round(std_spread * 10000, 4),
        "liquidity_cost": round(liquidity_cost, 6),
        "sample_size": len(spread_bps_series),
    }


def compute_liquidity_adjusted_var(
    price_var: float,
    spread_bps_series: list[float],
    position_value: float,
    z_score: float = DEFAULT_Z_SCORE,
) -> dict:
    """price_var: risk/limits/portfolio.py::PortfolioRiskEngine.portfolio_var()
    ile hesaplanmış GERÇEK parametrik VaR ($). Liquidity Cost ekleyip
    toplam LVaR'ı döner. Spread verisi yetersizse (fail-closed)
    liquidity_cost None, liquidity_adjusted_var SADECE price_var'a eşit
    döner — icat edilmiş bir sayı asla üretilmez, ama fiyat-riski hesabı
    sessizce kaybolmaz."""
    liquidity = compute_liquidity_cost(spread_bps_series, position_value, z_score)
    if liquidity is None:
        return {
            "price_var": round(price_var, 6),
            "liquidity_cost": None,
            "mean_spread_bps": None,
            "std_spread_bps": None,
            "liquidity_adjusted_var": round(price_var, 6),
            "sample_size": len(spread_bps_series),
        }
    return {
        "price_var": round(price_var, 6),
        "liquidity_cost": liquidity["liquidity_cost"],
        "mean_spread_bps": liquidity["mean_spread_bps"],
        "std_spread_bps": liquidity["std_spread_bps"],
        "liquidity_adjusted_var": round(price_var + liquidity["liquidity_cost"], 6),
        "sample_size": liquidity["sample_size"],
    }
