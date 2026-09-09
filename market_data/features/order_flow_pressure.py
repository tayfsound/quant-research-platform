"""Agresif Alış Baskısı (Order Flow Pressure) — Faz 461 (2026-09-09).

Kullanıcı isteği: "Sinyalleri yok etmek yerine orijinal sinyalleri çekip
versek sisteme daha iyi olmaz mı?" Faz 461'de doğrulandı ki Binance'in
klines cevabı her mumda `taker_buy_base`'i (agresif ALIŞ hacmi) zaten
gönderiyordu ve `_parse_klines()` onu atıyordu.

Bu modül, o ham veriyi KULLANILABİLİR bir sinyale çeviriyor. Kurgu
KEYFİ DEĞİL, inşa edilmeden önce canlı Binance verisiyle ölçüldü
(12 sembol, 33.750 pencere):

    ham hâli (tek mumun oranı -> 1sa sonrası)      separation −0,023 (değersiz)
    15dk toplulaştırılmış + 120dk normalize edilmiş:
        15 dakika ufku, üst %25 vs alt %25          separation −0,045
        15 dakika ufku, üst %10 vs alt %10          separation −0,075
        1 saat ufku                                 separation −0,002 (yok)

Üç sonuç mimariyi belirledi:
  1. PENCERELEME + NORMALİZASYON ŞART. Tek mumun ham oranı gürültü;
     sembolün kendi son normuna göre sapma anlamlı.
  2. ETKİN UFUK KISA (~15dk). 1 saatte sinyal tamamen kayboluyor —
     Kolm/Turiel/Westray (Mathematical Finance 2023) "etkin ufuk ≈ iki
     ortalama fiyat değişimi" bulgusuyla birebir uyumlu.
  3. İŞARET ORTALAMAYA-DÖNÜŞ YÖNÜNDE (uçlarda güçleniyor: −0,045 →
     −0,075). Yani AŞIRI agresif alış, sonraki 15 dakikada DÜŞÜŞ
     habercisi. Faz 460'ın genel örüntüsüyle tutarlı.

DİKKAT — mevcut `aggressive_buy_ratio` ile KARIŞTIRILMAMALI:
`market_data/ingestion/pipeline.py` zaten `/api/v3/trades`'in son 200
işleminden anlık bir oran hesaplıyor ve Faz 460'ta o sinyalin yön değeri
ÖLÇÜLDÜ: −0,011, yani "no_signal". Bu modül farklı bir şey yapıyor —
anlık bir enstantane değil, mum serisi üzerinden pencerelenmiş ve
sembolün kendi normuna göre normalize edilmiş bir sapma.

Kasıtlı olarak SADECE gözlem: çıktısı `ctx.market.features`'a yazılıyor
(Faz 436/437/438/439 İLE AYNI kanıtlanmış boru), hiçbir ajanın skoruna
girmiyor. Wire etme kararı, gerçek IC birikince AYRI bir onay turu.
"""
import statistics

DEFAULT_WINDOW = 15
DEFAULT_NORM_WINDOW = 120
# Normalizasyon penceresinin en az yarısı dolu olmalı; daha azıyla
# hesaplanan bir ortalama/sapma güvenilir değil.
MIN_NORM_COVERAGE = 0.5


def compute_taker_buy_ratios(candles: list[dict]) -> list[float | None]:
    """Her mum için agresif alış oranı = taker_buy_base / volume.
    Alan eksikse ya da hacim sıfırsa None — uydurma değer üretilmez
    (geçmiş mumlarda bu alanlar Faz 461 öncesinden NULL geliyor)."""
    ratios: list[float | None] = []
    for candle in candles:
        volume = candle.get("volume")
        taker_buy = candle.get("taker_buy_base")
        if not volume or volume <= 0 or taker_buy is None:
            ratios.append(None)
            continue
        ratio = taker_buy / volume
        # Binance verisinde oran tanımı gereği [0,1] aralığında olmalı;
        # dışına çıkan bir değer bozuk veridir, düzeltilmez, ELENİR.
        ratios.append(ratio if 0.0 <= ratio <= 1.0 else None)
    return ratios


def compute_order_flow_pressure(
    candles: list[dict],
    window: int = DEFAULT_WINDOW,
    norm_window: int = DEFAULT_NORM_WINDOW,
) -> dict | None:
    """candles: kronolojik (en eski -> en yeni) mum listesi; her mum
    `volume` ve `taker_buy_base` taşımalı.

    Döndürülenler:
      taker_buy_ratio    — son `window` mumun ortalama agresif alış oranı
      baseline           — önceki `norm_window` mumun ortalaması
      pressure_zscore    — ikisinin arasındaki sapmanın, pencere
                           ortalamasının KENDİ standart hatasına
                           bölünmüş hâli
      pressure_state     — "extreme_buying" / "buying" / "neutral" /
                           "selling" / "extreme_selling"

    ÖNEMLİ (bir ölçüm hatasından öğrenildi): `window` mumun ORTALAMASI,
    tek tek mumlardan ~sqrt(window) kat DAR bir dağılıma sahiptir. İlk
    ölçümde ortalama, tek-mum standart sapmasına bölündüğü için 33.750
    gözlemin yalnızca 39'u |z|>=1 çıktı ve sinyal görünmez oldu. Burada
    payda standart HATA (sd/sqrt(n)) — doğru ölçek bu.

    Veri yetmezse None (fail-closed)."""
    if len(candles) < norm_window + window:
        return None

    ratios = compute_taker_buy_ratios(candles)
    recent = [r for r in ratios[-window:] if r is not None]
    baseline_pool = [r for r in ratios[-(norm_window + window):-window] if r is not None]

    if len(recent) < window or len(baseline_pool) < norm_window * MIN_NORM_COVERAGE:
        return None

    recent_mean = statistics.mean(recent)
    baseline_mean = statistics.mean(baseline_pool)
    baseline_sd = statistics.pstdev(baseline_pool)
    if baseline_sd <= 0:
        return None

    standard_error = baseline_sd / (len(recent) ** 0.5)
    zscore = (recent_mean - baseline_mean) / standard_error

    if zscore >= 2.0:
        state = "extreme_buying"
    elif zscore >= 0.75:
        state = "buying"
    elif zscore <= -2.0:
        state = "extreme_selling"
    elif zscore <= -0.75:
        state = "selling"
    else:
        state = "neutral"

    return {
        "taker_buy_ratio": round(recent_mean, 6),
        "baseline": round(baseline_mean, 6),
        "pressure_zscore": round(zscore, 4),
        "pressure_state": state,
        "window": window,
        "norm_window": norm_window,
        "coverage": round(len(baseline_pool) / norm_window, 4),
    }
