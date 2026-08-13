"""Price Structure ve Market Geometry — Faz 344-368 (Cognitive Core 2.0).

market_data/features/signal_engine.py'nin compute_pattern_signals'ı zaten
BOS/CHoCH/FVG/swing_structure/liquidity_sweep/Fibonacci/Wyckoff'u
kapsıyor — bunların hiçbiri tek tek swing noktalarını birbirine göre
KÜMELEMİYOR. Bu modül, fiyatın GERÇEKTEN birden fazla kez tepki verdiği
(min_touches) destek/direnç BÖLGELERİNİ (tek bir keskin seviye değil,
tolerance_pct genişliğinde bir bant) tespit ediyor — klasik, standart bir
teknik analiz kavramı (S/R zone clustering), icat edilmiş bir yöntem
değil.

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir SL/TP/pozisyon kararını burada
otomatik değiştirmiyor."""
import numpy as np

from market_data.features.signal_engine import _find_swings
from market_data.ingestion.ohlcv import OHLCV

DEFAULT_TOLERANCE_PCT = 0.005  # %0.5 — aynı bölge sayılacak fiyat farkı
DEFAULT_MIN_TOUCHES = 2


def compute_support_resistance_zones(
    data: list[OHLCV],
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
    min_touches: int = DEFAULT_MIN_TOUCHES,
) -> dict:
    """Swing high/low'ları (signal_engine._find_swings ile AYNI tanım)
    tolerance_pct içinde kümeleyip, en az min_touches kez test edilmiş
    GERÇEK bölgeleri döner. <10 bar ile dürüstçe boş liste döner — icat
    edilmiş bir bölge asla üretilmez (fail-closed)."""
    if len(data) < 10:
        return {"support_zones": [], "resistance_zones": [], "current_price": None}

    closes = np.array([d.close for d in data], dtype=float)
    swing_highs, swing_lows = _find_swings(closes)

    resistance_zones = _cluster_levels([float(closes[i]) for i in swing_highs], tolerance_pct, min_touches)
    support_zones = _cluster_levels([float(closes[i]) for i in swing_lows], tolerance_pct, min_touches)

    return {
        "support_zones": support_zones,
        "resistance_zones": resistance_zones,
        "current_price": round(float(closes[-1]), 8),
    }


def _cluster_levels(levels: list[float], tolerance_pct: float, min_touches: int) -> list[dict]:
    if not levels:
        return []
    sorted_levels = sorted(levels)
    clusters: list[list[float]] = [[sorted_levels[0]]]
    for level in sorted_levels[1:]:
        if (level - clusters[-1][-1]) / clusters[-1][-1] <= tolerance_pct:
            clusters[-1].append(level)
        else:
            clusters.append([level])

    zones = []
    for cluster in clusters:
        if len(cluster) < min_touches:
            continue
        zones.append({
            "level": round(float(np.mean(cluster)), 8),
            "touches": len(cluster),
            "range_low": round(float(min(cluster)), 8),
            "range_high": round(float(max(cluster)), 8),
        })
    return sorted(zones, key=lambda z: z["touches"], reverse=True)
