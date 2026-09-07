"""SL Hata Ayrıştırması: Gerçek Yön Hatası vs Zamanlama Hatası — Faz 443
(2026-09-07). Bkz. /Users/emreturkes/.claude/plans/velvety-whistling-
parasol.md.

Bağlam: GPT'nin 1 numaralı önceliği — "Her SL için entry direction+MAE+
MFE+forward return hesapla, sonra ikiye ayır: (A) Gerçek direction error
(fiyat hiç hedefe yaklaşmadı) vs (B) Timing/execution error (neredeyse
kazanıyordu, hedefe çok yaklaşmıştı ama stop'a takıldı)." Bugün elle
yapılan bu ölçüm (MFE'nin hedefe olan GERÇEK mesafeyle normalize
edilmesi — sadece "biraz hareket etti mi" değil) çarpıcı bir sonuç
verdi: LONG'da %65,5, SHORT'ta %56,4 gerçek yön hatası (kullanıcının
ilk hatırladığı ~%47-51'lik kaba MFE>0 eşiğinden YÜKSEK) — sadece ~%20'si
"neredeyse kazanıyordu" türü zamanlama hatası.

`analytics/mae_mfe.py` İLE KARIŞTIRILMAMALI — o modül SL/TP yerleşimini
OPTİMİZE ediyor (hangi bariyer daha iyi olurdu), bu modül GERÇEKLEŞEN
bariyerle (mevcut take_profit_price) SL'in NEDEN olduğunu TEŞHİS
ediyor. `outcome.mfe_pct`'i (zaten Faz 268-sonrası her kapanan işlem
için hesaplanıyor) yeniden kullanıyor, yeni bir ölçüm makinesi değil.

Kasıtlı olarak SADECE teşhis/rapor — hiçbir canlı kararı etkilemiyor."""

DEFAULT_TIMING_ERROR_THRESHOLD = 0.5    # MFE, hedefin en az yarısına ulaşmış
DEFAULT_DIRECTION_ERROR_THRESHOLD = 0.1  # MFE, hedefin onda birine bile ulaşmamış


def classify_sl_error(
    mfe_pct: float | None,
    entry_price: float | None,
    take_profit_price: float | None,
    timing_error_threshold: float = DEFAULT_TIMING_ERROR_THRESHOLD,
    direction_error_threshold: float = DEFAULT_DIRECTION_ERROR_THRESHOLD,
) -> str | None:
    """mfe_pct: pozisyonun GERÇEKTEN yaşadığı maksimum lehte hareket
    (yüzde, `outcome.mfe_pct`). entry_price/take_profit_price: o
    pozisyonun GERÇEK hedefini kurmak için. mfe_to_target_ratio = mfe_pct
    / |take_profit_price - entry_price| / entry_price — bu oran hedefin
    NE KADARINA ulaşıldığını gösterir:
    - >= timing_error_threshold (varsayılan 0,5): "timing_error" — fiyat
      hedefin en az yarısına kadar gitmiş, gerçek bir yön hatası değil,
      stop/hedef yerleşimi ya da zamanlama sorunu.
    - < direction_error_threshold (varsayılan 0,1): "genuine_direction_
      error" — fiyat hedefe neredeyse hiç yaklaşmamış, entry anındaki
      yön tahmini muhtemelen gerçekten yanlıştı.
    - aradaki bant: "partial_move" — ne net bir zamanlama hatası ne net
      bir yön hatası, dürüstçe ayrılmamış bırakılıyor (icat edilmiş bir
      sınıflandırma yapılmıyor).

    Girdilerden biri eksik/dejenere ise (entry_price<=0, hedef entry'ye
    eşit) None — fail-closed, icat edilmiş bir sonuç asla üretilmez."""
    if mfe_pct is None or entry_price is None or take_profit_price is None or entry_price <= 0:
        return None
    target_distance_pct = abs(take_profit_price - entry_price) / entry_price
    if target_distance_pct <= 0:
        return None

    ratio = mfe_pct / target_distance_pct
    if ratio >= timing_error_threshold:
        return "timing_error"
    if ratio < direction_error_threshold:
        return "genuine_direction_error"
    return "partial_move"


def compute_sl_error_decomposition(records: list[dict]) -> dict:
    """records: her biri {'direction', 'mfe_pct', 'entry_price',
    'take_profit_price'} olan, GERÇEKTEN stop_loss ile kapanmış kararlar.
    Yöne göre ayrıştırılmış {direction: {n, pct_timing_error, pct_
    genuine_direction_error, pct_partial_move}} döner — sınıflandırma
    None dönen kayıtlar (fail-closed) hiçbir gruba dahil edilmez."""
    by_direction: dict[str, dict[str, int]] = {}
    for r in records:
        direction = r.get("direction")
        if direction not in ("LONG", "SHORT"):
            continue
        label = classify_sl_error(r.get("mfe_pct"), r.get("entry_price"), r.get("take_profit_price"))
        if label is None:
            continue
        bucket = by_direction.setdefault(direction, {"n": 0, "timing_error": 0, "genuine_direction_error": 0, "partial_move": 0})
        bucket["n"] += 1
        bucket[label] += 1

    result = {}
    for direction, bucket in by_direction.items():
        n = bucket["n"]
        result[direction] = {
            "n": n,
            "pct_timing_error": round(100.0 * bucket["timing_error"] / n, 1),
            "pct_genuine_direction_error": round(100.0 * bucket["genuine_direction_error"] / n, 1),
            "pct_partial_move": round(100.0 * bucket["partial_move"] / n, 1),
        }
    return result
