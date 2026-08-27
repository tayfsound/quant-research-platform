"""Direction × Regime Asymmetry'nin girdisini strategy_regime_compatibility_
gatherer'ın ZATEN topladığı gerçek veriden alan tek kaynak — Faz 364-devam.
Yeni bir DB sorgusu yok, sadece mevcut çıktının LONG/SHORT eşleştirmesi."""
from analytics.direction_regime_asymmetry import compute_direction_regime_asymmetry
from services.strategy_regime_compatibility_gatherer import gather_strategy_regime_compatibility


def gather_direction_regime_asymmetry() -> dict:
    base = gather_strategy_regime_compatibility()
    asymmetry = compute_direction_regime_asymmetry(base["by_strategy"])
    return {"by_strategy_base": asymmetry, "n_decisions_analyzed": base["n_decisions_analyzed"]}
