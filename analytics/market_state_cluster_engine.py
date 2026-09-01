"""Market State Cluster Engine — Faz 401 (Market State Katmanı Faz 1).

Tekil-sembol `market_data.features.market_state_engine::compute_market_
state()` okuması, altın kümesi bulgusunun (GC=F+XAUTUSDT, Concept Drift
araştırması, 2026-09-01) gösterdiği gibi paylaşılan bir rejim dönüşünü
gecikmeli görebilir — bu modül YENİ bir kümeleme algoritması İCAT
ETMİYOR, zaten canlı olan `risk/cross_symbol_correlation.py`'nin
(same_direction_correlation indirimini besleyen, gerçek veriyle
doğrulanmış — z=9.42, p≈0 — korelasyon matrisini) yeniden kullanıyor.

Kasıtlı olarak SADECE gözlem/ölçüm — hiçbir canlı kararı etkilemiyor."""
import numpy as np

from risk.cross_symbol_correlation import HIGH_CORRELATION_THRESHOLD, compute_correlation_matrix

MIN_CLUSTER_PEERS = 1


def compute_cluster_market_state(
    returns: dict[str, list[float]],
    per_symbol_states: dict[str, dict],
) -> dict[str, dict]:
    """returns: {symbol: [gerçek dönemsel getiri, ...]} — same_direction_
    correlation ile AYNI girdi şekli. per_symbol_states: {symbol:
    compute_market_state()'in çıktısı}. Her sembol için KENDİ market
    state'ine ek olarak `peer_count`/`cluster_agreement` (yüksek-korele
    eşlerin AYNI yönde olma oranı)/`cluster_reversing_fraction` (yüksek-
    korele eşlerin `reversing=True` olma oranı) döner. Yüksek-korele eş
    yoksa (`peer_count=0`) cluster alanları None — icat edilmiş bir
    kümeleme sonucu asla üretilmez."""
    symbols, corr = compute_correlation_matrix(returns)
    result: dict[str, dict] = {}
    for i, sym in enumerate(symbols):
        state = per_symbol_states.get(sym)
        if state is None:
            continue
        peer_indices = [
            j for j, other in enumerate(symbols)
            if other != sym and not np.isnan(corr[i, j]) and corr[i, j] > HIGH_CORRELATION_THRESHOLD
        ]
        if len(peer_indices) < MIN_CLUSTER_PEERS:
            result[sym] = {**state, "peer_count": 0, "cluster_agreement": None, "cluster_reversing_fraction": None}
            continue

        peer_symbols = [symbols[j] for j in peer_indices]
        peer_states = [per_symbol_states[p] for p in peer_symbols if p in per_symbol_states]
        if not peer_states:
            result[sym] = {**state, "peer_count": 0, "cluster_agreement": None, "cluster_reversing_fraction": None}
            continue

        same_direction = sum(1 for p in peer_states if p["direction"] == state["direction"])
        reversing_count = sum(1 for p in peer_states if p.get("reversing"))
        result[sym] = {
            **state,
            "peer_count": len(peer_states),
            "cluster_agreement": round(same_direction / len(peer_states), 4),
            "cluster_reversing_fraction": round(reversing_count / len(peer_states), 4),
        }
    return result
