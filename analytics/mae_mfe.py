"""MAE/MFE ölçüm katmanı — Predictive Decision Architecture'ın ilk, somut
dilimi (davranış değişikliği yok, sadece ölçüm).

Kullanıcının önerisi: sadece entry/exit/pnl saklamak yetmez — işlem
açıldıktan kapanana kadar fiyatın yaptığı GERÇEK maksimum olumlu
(MFE — Maximum Favorable Excursion) ve olumsuz (MAE — Maximum Adverse
Excursion) hareketi ölçmeliyiz. Bu, "SL neden oluyor?" sorusunu
parçalamanın ilk adımı: SL olan ama MFE'si yüksek bir işlem ("aslında
TP'ye gidecek potansiyeli vardı, SL çok dardı") ile MAE'si zaten büyük
bir işlem ("giriş kötüydü, SL'nin suçu yok") arasındaki fark, ancak bu
ölçümle ayırt edilebilir.

Kasıtlı olarak SADECE ölçüm — hiçbir SL/TP/pozisyon büyüklüğü kararını
otomatik değiştirmiyor. Koşullu dağılımlar (rejim/güven/sembol bazlı
quantile'lar), competing-risks modeli ve EV-tabanlı bariyer optimizasyonu
ayrı, sonraki adımlar (bkz. todo listesi)."""
from market_data.ingestion.ohlcv import OHLCV


def compute_mae_mfe(direction: str, entry_price: float, bars: list[OHLCV]) -> dict:
    """bars: pozisyonun GERÇEKTEN açık kaldığı süre boyunca (entry bar'ı
    dahil, exit bar'ına kadar) gerçek OHLCV geçmişi — walk-forward
    backtest'in zaten bellekte tuttuğu dilim, ekstra bir ağ isteği
    gerekmiyor.

    MAE: pozisyon ALEYHİNE en kötü anlık (unrealized) hareket — LONG için
    en düşük low, SHORT için en yüksek high, entry'ye göre yüzde.
    MFE: pozisyon LEHİNE en iyi anlık hareket — LONG için en yüksek high,
    SHORT için en düşük low.

    time_to_mae_seconds/time_to_mfe_seconds: bu ekstremum'a ulaşılan
    bar'ın entry'den ne kadar süre sonra gerçekleştiği — "kayıp hemen mi
    oldu yoksa uzun süre mi dayandı" sorusunu ayırt etmek için.

    entry_price<=0 ya da bars boşsa dürüstçe None'lar döner — icat
    edilmiş bir sayı üretilmez (fail-closed)."""
    if entry_price <= 0 or not bars:
        return {
            "mae_pct": None, "mfe_pct": None,
            "time_to_mae_seconds": None, "time_to_mfe_seconds": None,
        }

    entry_time = bars[0].timestamp
    worst_pct = 0.0
    best_pct = 0.0
    time_to_mae = 0.0
    time_to_mfe = 0.0

    for bar in bars:
        if direction == "LONG":
            adverse_pct = (bar.low - entry_price) / entry_price   # negatif = zararda
            favorable_pct = (bar.high - entry_price) / entry_price  # pozitif = kârda
        else:
            adverse_pct = (entry_price - bar.high) / entry_price
            favorable_pct = (entry_price - bar.low) / entry_price

        elapsed = (bar.timestamp - entry_time).total_seconds()

        if adverse_pct < worst_pct:
            worst_pct = adverse_pct
            time_to_mae = elapsed
        if favorable_pct > best_pct:
            best_pct = favorable_pct
            time_to_mfe = elapsed

    return {
        "mae_pct": round(worst_pct, 6),
        "mfe_pct": round(best_pct, 6),
        "time_to_mae_seconds": time_to_mae,
        "time_to_mfe_seconds": time_to_mfe,
    }
