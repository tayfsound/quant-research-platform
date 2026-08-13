"""Stablecoin/Pegged-Asset Depeg Risk.

Watchlist'teki bazı semboller bir referans varlığa SABİT fiyatta kalması
BEKLENEN "pegged" varlıklar: XAUTUSDT/PAXGUSDT gerçek spot altına (GC=F),
USDCUSDT gerçek 1.00 USD'ye. Peg kırıldığında (gerçek fiyat referanstan
anlamlı ölçüde saparsa) bu hem kendi başına bir risk sinyali (ihraççı
güveni/likidite sorunu) hem de watchlist'teki DİĞER USDT-kotasyonlu tüm
sembollerin fiyatının GERÇEKTE ne kadar güvenilir olduğunu etkiler (her
şey USDT cinsinden fiyatlanıyor, USDT'nin kendisi sapıyorsa hepsi
etkilenir).

Kasıtlı olarak SADECE tespit/rapor — hiçbir pozisyon/risk kararını
otomatik değiştirmiyor."""

DEFAULT_DEPEG_THRESHOLD_PCT = 0.005  # %0.5 — stablecoin/altın-pegged varlıklar için standart alarm eşiği


def compute_depeg_deviation(pegged_price: float | None, reference_price: float | None) -> dict | None:
    """pegged_price: pegli varlığın GERÇEK piyasa fiyatı (ör. XAUTUSDT'nin
    Binance'teki son kapanışı). reference_price: peg'in dayandığı GERÇEK
    referans fiyat (ör. GC=F spot ons başına, ya da USD-pegged varlıklar
    için 1.0). Birim dönüşümü (varsa) çağıran tarafın sorumluluğu — bu
    fonksiyon SADECE oranı hesaplar. reference_price None/<=0 ya da
    pegged_price None ise fail-closed None döner — icat edilmiş bir sapma
    asla üretilmez."""
    if pegged_price is None or reference_price is None or reference_price <= 0:
        return None
    deviation_pct = (pegged_price - reference_price) / reference_price
    return {
        "pegged_price": round(pegged_price, 8),
        "reference_price": round(reference_price, 8),
        "deviation_pct": round(deviation_pct, 6),
        "depeg_detected": bool(abs(deviation_pct) > DEFAULT_DEPEG_THRESHOLD_PCT),
    }
