"""Pivot-Mesafe Kapısı — backlog #17, saf (pure) hesaplama katmanı.

Kullanıcı isteği: "tepeden/dipten kovalıyorsa" (kritik bir seviyeden
uzaktaysa) giriş engellensin. Gerçek veriyle (450+ kapanmış karar,
`market_data/features/signal_engine.py::compute_pivot_points`'in günlük
klasik pivot seviyeleri — kodda vardı ama hiç kullanılmıyordu) doğru
eşik bulundu: large-cap'te (`services/agent_memory.py::crypto_cap_tier`)
mesafe arttıkça win_rate ~%0.55'e kadar sabit (%91-96), %0.65'ten sonra
~%91'e, %2.20'de ~%84'e düşüyor — gerçek, monotonik bir kırılma.
Small-cap'te AYNI desen YOK/TERS (en yakın grup en kötü) — bu yüzden
gate SADECE large-cap'e uygulanıyor, small-cap'e hiç dokunmuyor."""

DEFAULT_THRESHOLD_PCT = 0.006  # gerçek veriyle kalibre edildi (D7 ~%0.55 iyi, D8 ~%0.72 kötü)


def compute_nearest_pivot_distance_pct(pivot_levels: dict | None, current_price: float) -> float | None:
    """pivot_levels: signal_engine.compute_pivot_points()'ün "pivot_classic"
    alt-sözlüğü (P/R1/R2/R3/S1/S2/S3). current_price'ın bu 7 seviyeden
    en yakınına, fiyatın kendisine oranla mesafesi. Veri yoksa/geçersizse
    None (fail-closed — gate bu durumda hiçbir şeyi engellemez, "bilmiyorum"
    "engelle" anlamına gelmez)."""
    if not pivot_levels or current_price <= 0:
        return None
    levels = [v for v in pivot_levels.values() if v is not None]
    if not levels:
        return None
    nearest = min(levels, key=lambda lvl: abs(lvl - current_price))
    return abs(current_price - nearest) / current_price


def is_pivot_distance_entry_blocked(
    is_large_cap: bool,
    distance_pct: float | None,
    threshold_pct: float = DEFAULT_THRESHOLD_PCT,
) -> bool:
    """True dönerse giriş "kritik bir seviyeden çok uzak" olduğu için
    engellenmeli. SADECE large-cap sembollerde uygulanır — gerçek veri
    small-cap'te bu ilişkinin tersine döndüğünü/hiç olmadığını gösterdi
    (bkz. modül dosyası docstring'i). distance_pct None ise (pivot
    hesaplanamadıysa) fail-closed DEĞİL — engellenmez, çünkü bu kapı
    SADECE doğrulanmış bir aşırılığı hedefliyor, veri eksikliğini genel
    bir yasağa çevirmiyor (pyramid_regime_gate'in aksine — o farklı bir
    risk sınıfı, orası fail-closed olmak ZORUNDA)."""
    if not is_large_cap or distance_pct is None:
        return False
    return distance_pct > threshold_pct
