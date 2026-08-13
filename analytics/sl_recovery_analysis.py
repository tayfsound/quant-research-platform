"""SL Sonrası Fiyat Geri Dönüşü — Faz 268-sonrası (kullanıcı isteği).

analytics/mae_mfe.py::compute_mae_mfe() pozisyon KAPANANA kadarki gerçek
yolu ölçüyor; compute_optimal_barrier() de bu AYNI pencere içinde farklı
bir SL/TP varsayımıyla "ne olurdu" soruyor — ama HİÇBİRİ kapanıştan
SONRASINA bakmıyor. Bu modül tam olarak o soruyu soruyor: "SL'e
gittikten sonra fiyat gerçekten geri döndü mü, ne kadar sürede, arada
ne kadar daha derine gitti?"

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir gerçek pozisyonu YENİDEN
AÇMIYOR, hiçbir stop mesafesini otomatik DEĞİŞTİRMİYOR, hiçbir yere wire
edilmiyor."""


def compute_post_exit_recovery(
    direction: str,
    entry_price: float,
    post_exit_bars: list,
    target_pct: float | None = None,
) -> dict:
    """post_exit_bars: SL'in tetiklendiği andan SONRAKİ (çağıran tarafın
    sorumluluğu — exit bar'ı dahil edilmemeli) GERÇEK OHLCV bar geçmişi,
    kronolojik sırayla. Fiyatın entry_price'a (breakeven) geri dönüp
    dönmediğini, dönerse ne kadar sürede (saniye) ve arada ne kadar daha
    derine gittiğini (worst_pct_after_exit — entry'ye göre, exit'ten
    sonraki en kötü nokta) hesaplar. target_pct verilirse (ör. o
    pozisyonun gerçek take_profit yüzdesi), breakeven yerine o hedefe
    ulaşılıp ulaşılmadığı da ayrıca raporlanır.

    post_exit_bars boşsa ya da entry_price<=0 ise fail-closed None'lar
    döner — icat edilmiş bir sayı üretilmez."""
    if entry_price <= 0 or not post_exit_bars:
        return {
            "recovered_to_breakeven": None,
            "time_to_recovery_seconds": None,
            "worst_pct_after_exit": None,
            "reached_target": None,
            "time_to_target_seconds": None,
        }

    exit_time = post_exit_bars[0].timestamp
    worst_pct = 0.0
    recovered_at = None
    target_hit_at = None

    for bar in post_exit_bars:
        if direction == "LONG":
            low_pct = (bar.low - entry_price) / entry_price
            high_pct = (bar.high - entry_price) / entry_price
            worst_pct = min(worst_pct, low_pct)
            if recovered_at is None and bar.high >= entry_price:
                recovered_at = bar.timestamp
            if target_pct is not None and target_hit_at is None and high_pct >= target_pct:
                target_hit_at = bar.timestamp
        else:  # SHORT
            low_pct = (entry_price - bar.high) / entry_price
            high_pct = (entry_price - bar.low) / entry_price
            worst_pct = min(worst_pct, low_pct)
            if recovered_at is None and bar.low <= entry_price:
                recovered_at = bar.timestamp
            if target_pct is not None and target_hit_at is None and high_pct >= target_pct:
                target_hit_at = bar.timestamp

    return {
        "recovered_to_breakeven": recovered_at is not None,
        "time_to_recovery_seconds": (
            (recovered_at - exit_time).total_seconds() if recovered_at is not None else None
        ),
        "worst_pct_after_exit": round(worst_pct, 6),
        "reached_target": (target_hit_at is not None) if target_pct is not None else None,
        "time_to_target_seconds": (
            (target_hit_at - exit_time).total_seconds() if target_hit_at is not None else None
        ),
    }
