"""Yön Becerisi Ölçümü — Faz 458 (2026-09-09).

Bağlam (kullanıcı isteği: "Sürekli bir direction problemimiz var, bunu
aşmadan ilerleyemeyiz"). Faz 446 direction Brier'ini 0,271 ölçüp
"rastgeleden kötü" dedi ama BU TEK SAYI NE YAPMAMIZ GEREKTİĞİNİ
SÖYLEMİYOR. Bu modül, 2026-09-08 akşamı yapılan akademik literatür
taramasının üç metodolojik düzeltmesini kalıcı, test edilmiş saf
fonksiyonlara çeviriyor. Hiçbiri yeni bir "metrik icadı" değil, hepsi
literatürde tanımlı standart araçlar.

1) MURPHY AYRIŞTIRMASI (Murphy 1973). Brier = Reliability − Resolution
   + Uncertainty. Kural: bir tahmin ancak Resolution > Reliability ise
   değerlidir. Gerçek veride ölçüldü (n=7.720, 21 gün, 1sa ufuk):
   Uncertainty 0,2440 / Reliability 0,0316 / Resolution 0,000108 —
   Reliability, Resolution'ın 292 KATI. Bu, "sabit olasılık yayınlayan,
   hiç ayrım yapmayan tahmin"in ders kitabı tanımı.
   KRİTİK SONUÇ (bir tuzak uyarısı): post-hoc kalibrasyon (Platt/
   isotonic) Brier'i anında 0,2754 → 0,2439'a indirir, yani "rastgeleden
   kötü" manşeti kaybolur — AMA SIFIR BİLGİ EKLENMİŞ OLUR. Tek bir Brier
   sayısı bu iki bileşeni birbirinden ayıramadığı için aylardır yanlış
   soruyu tartışıyorduk.

2) DOĞRU KIYAS NOKTASI. Yön isabeti tek başına yanıltıcı: hedef dengesiz
   olduğunda sadece pozitif bir bias bile %50 üstü isabet üretir. Doğru
   benchmark %50 DEĞİL, AYNI ÖRNEKLEMDEKİ koşulsuz yükseliş oranı
   (Goyal-Welch/Campbell-Thompson'ın "tarihsel ortalamayı geçebiliyor
   musun" disiplininin yön karşılığı). Gerçek veride: piyasa %51,94
   yükselmiş; LONG isabetimiz %45,50 (−6,4pp), SHORT %36,20 (−11,9pp).
   Yani sorunumuz "edge yok" değil, SİSTEMATİK NEGATİF edge.

3) PESARAN-TIMMERMANN (1992). Yön isabetinin anlamlılığı için standart
   non-parametrik test — bugüne kadar HİÇ çalıştırmadık. Ham hâli
   gözlemleri bağımsız varsayar; bizim 123 sembollük veri setimizde AYNI
   piyasa hareketi defalarca sayıldığı için (López de Prado'nun
   uniqueness problemi) bu varsayım İHLAL EDİLİYOR. Bu yüzden modül PT'yi
   tek başına bırakmıyor: `compute_daily_sign_test()` her GÜNÜ tek bir
   bağımsız gözlem sayan, çok daha muhafazakâr bir işaret testi sunuyor.
   Gerçek veride 6 yoğun günün 6'sında da her iki yön negatifti
   (p≈0,016) — örtüşme itirazını aşan asıl kanıt bu.

Kasıtlı olarak SADECE ölçüm — hiçbir canlı kararı etkilemiyor.
"""
import math

MIN_SAMPLE_SIZE = 30
DEFAULT_BINS = 10


def compute_murphy_decomposition(
    predictions: list[tuple[float, bool]], n_bins: int = DEFAULT_BINS,
) -> dict | None:
    """predictions: [(tahmin edilen olasılık, gerçek sonuç doğru muydu), ...]
    — `analytics/direction_prediction_v2.py::compute_brier_score()` ile
    BİREBİR AYNI girdi sözleşmesi (o modülün yerine geçmiyor, onu
    açıklıyor: aynı Brier'i üç bileşenine ayırıyor).

    Döndürülenler:
      reliability  — kalibrasyon hatası (KÜÇÜK iyi). Post-hoc
                     kalibrasyonla ~sıfırlanabilir, bilgi gerektirmez.
      resolution   — tahminin taşıdığı GERÇEK ayırt edici bilgi (BÜYÜK
                     iyi). Sadece gerçek öngörü gücüyle kazanılır.
      uncertainty  — verinin indirgenemez belirsizliği (taban oranın
                     Brier'i). Model ne yaparsa yapsın değişmez.
      brier_skill_score — 1 − Brier/Uncertainty. Sıfır = taban oranı
                     tahmin etmekle aynı, NEGATİF = ondan daha kötü.
      calibrated_brier_floor — kalibrasyon mükemmel olsaydı ulaşılacak
                     Brier (uncertainty − resolution). "Kalibrasyonu
                     düzeltirsek ne kazanırız" sorusunun tam cevabı.

    Ayrıştırma, tahminleri n_bins eşit genişlikli kovaya bölerek yapılır
    (standart yöntem). DÜRÜSTLÜK NOTU: kova içi olasılık varyansı küçük
    bir yanlılık yaratır (Ferro & Fricker 2012'nin bias-corrected
    versiyonu bunu düzeltiyor, burada UYGULANMADI) — bileşenlerin
    toplamı Brier'i birebir verir ama reliability bir miktar yukarı,
    resolution bir miktar aşağı sapabilir. Kova sayısı arttıkça sapma
    büyür; bu yüzden varsayılan 10'da bırakıldı.

    <MIN_SAMPLE_SIZE gözlemle fail-closed None (icat edilmiş bir
    ayrıştırma asla üretilmez)."""
    if len(predictions) < MIN_SAMPLE_SIZE:
        return None

    n = len(predictions)
    base_rate = sum(1 for _, outcome in predictions if outcome) / n

    bins: dict[int, list[tuple[float, bool]]] = {}
    for prob, outcome in predictions:
        # 1.0 tam sınırdaki tahmin son kovaya düşmeli (aksi halde n_bins.
        # kova taşar) -- min() bunu garanti ediyor.
        idx = min(int(prob * n_bins), n_bins - 1)
        bins.setdefault(idx, []).append((prob, outcome))

    reliability = 0.0
    resolution = 0.0
    for members in bins.values():
        n_k = len(members)
        mean_forecast = sum(p for p, _ in members) / n_k
        observed_rate = sum(1 for _, o in members if o) / n_k
        reliability += n_k * (mean_forecast - observed_rate) ** 2
        resolution += n_k * (observed_rate - base_rate) ** 2
    reliability /= n
    resolution /= n

    uncertainty = base_rate * (1 - base_rate)
    # Brier GERÇEK tanımından hesaplanıyor, bileşenlerden TÜRETİLMİYOR.
    # Sebebi bir testte yakalandı: kova İÇİ olasılık varyansı varsa klasik
    # üç terimli ayrıştırma gerçek Brier'i tam kurmaz (rastgele veride
    # ~0,001 fark ölçüldü). Bileşenlerden türetseydik, sessizce YANLIŞ bir
    # Brier raporlardık; artık fark `decomposition_residual` olarak AÇIKÇA
    # görünüyor ve kova sayısı arttıkça büyüdüğü izlenebiliyor.
    brier = sum((p - (1.0 if outcome else 0.0)) ** 2 for p, outcome in predictions) / n
    residual = brier - (reliability - resolution + uncertainty)

    return {
        "brier_score": round(brier, 6),
        "decomposition_residual": round(residual, 6),
        "reliability": round(reliability, 6),
        "resolution": round(resolution, 6),
        "uncertainty": round(uncertainty, 6),
        # uncertainty=0 (tüm sonuçlar aynı) dejenere durumunda bölme yok --
        # fail-closed None, uydurma bir skill skoru değil.
        "brier_skill_score": (
            round(1 - brier / uncertainty, 6) if uncertainty > 0 else None
        ),
        "calibrated_brier_floor": round(uncertainty - resolution, 6),
        "resolution_exceeds_reliability": bool(resolution > reliability),
        "base_rate": round(base_rate, 6),
        "sample_size": n,
        "bins_used": len(bins),
    }


def compute_benchmark_relative_skill(records: list[dict]) -> dict | None:
    """records: [{"direction": "LONG"|"SHORT", "forward_label": "UP"|"DOWN"}, ...]
    NEUTRAL etiketli kayıtlar ÇAĞIRAN tarafından elenmiş olmalı (bu modül
    "yönü doğru mu bildi" sorusunu ölçüyor, fiyat hareket etmediğinde
    soru anlamsız — Faz 441/446 ile AYNI fail-closed ilke).

    Her yönü KENDİ doğru benchmark'ıyla kıyaslar:
      LONG  -> aynı örneklemdeki koşulsuz YÜKSELİŞ oranı
      SHORT -> aynı örneklemdeki koşulsuz DÜŞÜŞ oranı (1 − yükseliş)
    Pozitif `skill` = benchmark'ı geçtik, negatif = benchmark'ın altında.

    DÜRÜSTLÜK NOTU (önemli): benchmark, kendi seçtiğimiz anlar DAHİL tüm
    örneklem üzerinden hesaplanıyor. Kararlarımızın ~%65'i LONG olduğu
    için koşulsuz yükseliş oranı kendi davranışımızla bir miktar
    kirleniyor. Daha temizi "seçmediğimiz anlar" üzerinden hesaplamak
    olurdu ama o kümeyi (her sembol × her dakika) tutmuyoruz; bu, eldeki
    veriyle mümkün olan en dürüst benchmark ve %50 varsaymaktan çok daha
    doğru."""
    usable = [
        r for r in records
        if r.get("direction") in ("LONG", "SHORT") and r.get("forward_label") in ("UP", "DOWN")
    ]
    if len(usable) < MIN_SAMPLE_SIZE:
        return None

    n = len(usable)
    up_rate = sum(1 for r in usable if r["forward_label"] == "UP") / n

    per_direction: dict[str, dict] = {}
    for direction, benchmark, winning_label in (
        ("LONG", up_rate, "UP"),
        ("SHORT", 1 - up_rate, "DOWN"),
    ):
        subset = [r for r in usable if r["direction"] == direction]
        if not subset:
            continue
        hit_rate = sum(1 for r in subset if r["forward_label"] == winning_label) / len(subset)
        per_direction[direction] = {
            "n": len(subset),
            "hit_rate": round(hit_rate, 6),
            "benchmark": round(benchmark, 6),
            "skill": round(hit_rate - benchmark, 6),
        }

    overall_hits = sum(
        1 for r in usable
        if (r["direction"] == "LONG" and r["forward_label"] == "UP")
        or (r["direction"] == "SHORT" and r["forward_label"] == "DOWN")
    )
    overall_hit_rate = overall_hits / n
    # Karışık bir yön dağılımının doğru benchmark'ı, yönlerin GERÇEK
    # payıyla ağırlıklı benchmark -- yoksa çok LONG'lu bir örneklemde
    # sayı yapay olarak iyi/kötü görünür.
    long_share = per_direction.get("LONG", {}).get("n", 0) / n
    blended_benchmark = long_share * up_rate + (1 - long_share) * (1 - up_rate)

    return {
        "unconditional_up_rate": round(up_rate, 6),
        "per_direction": per_direction,
        "overall": {
            "n": n,
            "hit_rate": round(overall_hit_rate, 6),
            "benchmark": round(blended_benchmark, 6),
            "skill": round(overall_hit_rate - blended_benchmark, 6),
        },
    }


def compute_pesaran_timmermann(records: list[dict]) -> dict | None:
    """Pesaran & Timmermann (1992) yön tahmini anlamlılık testi.

    records: `compute_benchmark_relative_skill()` ile AYNI sözleşme.
    Tahmin "yukarı mı" (LONG=True/SHORT=False) ile gerçek "yukarı mı"
    (UP=True/DOWN=False) ikilisi üzerinden çalışır.

    S = (P − P*) / sqrt(V(P) − V(P*)) ~ N(0,1), burada P gerçek isabet
    oranı, P* bağımsızlık varsayımı altındaki beklenen isabet oranı.
    Pozitif S = gerçek öngörü gücü; NEGATİF S = sistematik ters yön
    (bizim durumumuz) — bu yüzden p-değeri ÇİFT TARAFLI hesaplanıyor,
    literatürdeki tek taraflı standart kullanım DEĞİL: biz "beceri var
    mı" değil, "beceri sıfırdan farklı mı" sorusunu soruyoruz.

    KRİTİK UYARI: test gözlemlerin bağımsızlığını varsayar. Bizim veri
    setimizde 123 sembolün aynı piyasa hareketini paylaşması nedeniyle bu
    varsayım ihlal ediliyor ve p-değeri GERÇEKTE OLDUĞUNDAN ANLAMLI
    görünür. `compute_daily_sign_test()` bunun muhafazakâr karşılığı;
    ikisi birlikte raporlanmalı, PT tek başına asla."""
    usable = [
        r for r in records
        if r.get("direction") in ("LONG", "SHORT") and r.get("forward_label") in ("UP", "DOWN")
    ]
    if len(usable) < MIN_SAMPLE_SIZE:
        return None

    n = len(usable)
    predicted_up = [r["direction"] == "LONG" for r in usable]
    actual_up = [r["forward_label"] == "UP" for r in usable]

    p_hit = sum(1 for x, y in zip(predicted_up, actual_up) if x == y) / n
    px = sum(1 for x in predicted_up if x) / n
    py = sum(1 for y in actual_up if y) / n
    p_star = py * px + (1 - py) * (1 - px)

    var_p = p_star * (1 - p_star) / n
    var_p_star = (
        ((2 * py - 1) ** 2) * px * (1 - px) / n
        + ((2 * px - 1) ** 2) * py * (1 - py) / n
        + 4 * px * py * (1 - px) * (1 - py) / (n * n)
    )
    denominator = var_p - var_p_star
    if denominator <= 0:
        # Dejenere durum (ör. tüm tahminler tek yön) -- uydurma bir
        # istatistik üretmek yerine fail-closed.
        return None

    statistic = (p_hit - p_star) / math.sqrt(denominator)
    p_value = math.erfc(abs(statistic) / math.sqrt(2))

    return {
        "statistic": round(statistic, 6),
        "p_value": round(p_value, 8),
        "hit_rate": round(p_hit, 6),
        "expected_hit_rate_under_independence": round(p_star, 6),
        "sample_size": n,
        "significant_at_5pct": bool(p_value < 0.05),
        "direction_of_skill": (
            "positive" if statistic > 0 else "negative" if statistic < 0 else "none"
        ),
        "independence_assumption_violated": True,  # bkz. docstring
    }


def compute_daily_sign_test(records: list[dict], min_records_per_day: int = 50) -> dict | None:
    """Örtüşen örneklem itirazını aşan MUHAFAZAKÂR test: her GÜN tek bir
    bağımsız gözlem sayılır.

    records: `compute_benchmark_relative_skill()` sözleşmesi + "day"
    alanı (date ya da 'YYYY-MM-DD' string).

    Her gün için o günün KENDİ koşulsuz yükseliş oranına karşı beceri
    hesaplanır (piyasa rejimi günden güne değiştiği için sabit bir
    benchmark yanıltıcı olurdu), sonra "kaç günde beceri negatif" sorusu
    p=0,5 iki taraflı binom işaret testiyle sınanır.

    min_records_per_day altındaki günler ATILIR — 3 kararlık bir gün
    "gün" sayılırsa test gürültüyle dolar (gerçek veride 21 günün
    yalnızca 6'sı yoğundu, geri kalanı 1-50 karar arası)."""
    by_day: dict[str, list[dict]] = {}
    for r in records:
        if r.get("direction") not in ("LONG", "SHORT") or r.get("forward_label") not in ("UP", "DOWN"):
            continue
        day = r.get("day")
        if day is None:
            continue
        by_day.setdefault(str(day), []).append(r)

    daily: list[dict] = []
    for day, day_records in sorted(by_day.items()):
        if len(day_records) < min_records_per_day:
            continue
        day_n = len(day_records)
        day_up_rate = sum(1 for r in day_records if r["forward_label"] == "UP") / day_n
        hits = sum(
            1 for r in day_records
            if (r["direction"] == "LONG" and r["forward_label"] == "UP")
            or (r["direction"] == "SHORT" and r["forward_label"] == "DOWN")
        )
        long_n = sum(1 for r in day_records if r["direction"] == "LONG")
        long_share = long_n / day_n
        benchmark = long_share * day_up_rate + (1 - long_share) * (1 - day_up_rate)
        daily.append({
            "day": day, "n": day_n,
            "hit_rate": round(hits / day_n, 6),
            "benchmark": round(benchmark, 6),
            "skill": round(hits / day_n - benchmark, 6),
        })

    if len(daily) < 3:
        # 2 günle işaret testi anlamsız (en iyi ihtimalle p=0,5).
        return None

    negative_days = sum(1 for d in daily if d["skill"] < 0)
    positive_days = sum(1 for d in daily if d["skill"] > 0)
    n_days = negative_days + positive_days
    if n_days == 0:
        # Her günün becerisi TAM sıfır (ör. hep benchmark'la aynı) --
        # None döndürmek per_day kırılımını da kaybettirirdi, oysa bu
        # geçerli ve bilgilendirici bir sonuç: hiçbir yönde sapma yok.
        p_value = 1.0
    else:
        extreme = max(negative_days, positive_days)
        # İki taraflı binom işaret testi, p=0,5.
        tail = sum(math.comb(n_days, k) for k in range(extreme, n_days + 1)) / (2 ** n_days)
        p_value = min(1.0, 2 * tail)

    return {
        "days_evaluated": len(daily),
        "negative_skill_days": negative_days,
        "positive_skill_days": positive_days,
        "p_value": round(p_value, 6),
        "significant_at_5pct": bool(p_value < 0.05),
        "consistent_direction": (
            "negative" if negative_days == n_days
            else "positive" if positive_days == n_days
            else "mixed"
        ),
        "per_day": daily,
    }
