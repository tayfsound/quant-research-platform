"""TP/SL Confluence — Faz 299. Kullanıcı isteği (2026-08-19): "bu grup
A'da birazdan uygulayacağımız yaklaşımı başka teknik analiz araçları ile
çeşitlendiremez miyiz... hepsini değerlendirip hepsinden istatistiksel
olarak ortalama makul bir değer alıp deneyebiliriz belki." Verilen görüş
(kullanıcı kabul etti): literal ortalama metodolojik olarak kusurlu
(farklı ölçek/dağılımdaki yöntemleri kör bir aritmetik ortalamaya
sokmak) — doğru yaklaşım "zone of agreement": birden fazla BAĞIMSIZ
yöntemin (S/R zone clustering, Volume Profile POC/Value Area, Pivot
Points, Donchian, Keltner) fiyatta AYNI bölgede birleştiği yerler, kaç
yöntemin katıldığına göre doğal bir güç sıralaması taşır — icat edilmiş
bir ağırlıklandırma değil, "kaç bağımsız kanıt aynı fikirde" sayımı.

Kasıtlı olarak SADECE ölçüm/rapor — RiskTargetStage'in gerçek stop/target
hesabını burada henüz DEĞİŞTİRMİYOR. Kullanıcının kendi tek-tek/gözlem-
pencereli aktivasyon disiplinine göre, bu ölçüm katmanı önce mevcut ATR-
tabanlı hedefin gerçek yapısal desteğe ne sıklıkla denk geldiğini
gösteriyor — canlıya bağlanma kararı bu veriye bakıldıktan SONRA."""


def compute_confluence_zones(price_levels: dict[str, float], tolerance_pct: float = 0.005) -> list[dict]:
    """price_levels: {yöntem_adı: gerçek fiyat seviyesi} — S/R zone,
    Volume Profile POC/VA, Pivot Points, Donchian, Keltner gibi BAĞIMSIZ
    yöntemlerden gelen ham fiyatlar. tolerance_pct (varsayılan %0.5)
    içinde kümelenen seviyeler bir "confluence zone" oluşturur —
    method_count, kaç BAĞIMSIZ yöntemin bu bölgede birleştiğinin
    doğrudan sayımı (literal ortalama değil). Boş girdide fail-closed
    boş liste döner."""
    if not price_levels:
        return []

    items = sorted(price_levels.items(), key=lambda kv: kv[1])
    clusters: list[list[tuple[str, float]]] = [[items[0]]]
    for name, price in items[1:]:
        prev_price = clusters[-1][-1][1]
        if prev_price > 0 and (price - prev_price) / prev_price <= tolerance_pct:
            clusters[-1].append((name, price))
        else:
            clusters.append([(name, price)])

    zones = []
    for cluster in clusters:
        prices = [p for _, p in cluster]
        methods = [n for n, _ in cluster]
        zones.append({
            "level": round(sum(prices) / len(prices), 8),
            "contributing_methods": methods,
            "method_count": len(methods),
        })
    return sorted(zones, key=lambda z: z["method_count"], reverse=True)


def find_nearby_confluence_zone(
    price: float,
    zones: list[dict],
    tolerance_pct: float = 0.005,
    min_method_count: int = 2,
) -> dict | None:
    """Verilen bir fiyatın (ör. ATR-tabanlı hesaplanmış stop/target),
    en az min_method_count BAĞIMSIZ yöntemin birleştiği gerçek bir
    confluence bölgesine (tolerance_pct içinde) yakın olup olmadığını
    kontrol eder. price<=0 ya da eşleşme yoksa None (fail-closed)."""
    if price <= 0:
        return None
    for zone in zones:
        if zone["method_count"] < min_method_count:
            continue
        if abs(price - zone["level"]) / price <= tolerance_pct:
            return zone
    return None


def compute_price_levels(hourly_data, daily_data, current_price: float) -> dict[str, float]:
    """Zaten fetch edilmiş OHLCV geçmişinden (hourly_data: S/R/Volume
    Profile/Donchian/Keltner/Bollinger/Fibonacci için, daily_data: Pivot
    Points için) YEDİ BAĞIMSIZ yöntemin ham fiyat seviyelerini toplar.
    Her yöntem eksik/yetersiz veriyle fail-closed None dönebilir — o
    yöntem sessizce atlanır, hiçbir seviye icat edilmez. services/
    tp_sl_confluence_gatherer.py (ölçüm) ve services/orchestrator.py
    (canlı karar hattı) AYNI bu fonksiyonu çağırır — iki farklı yerde
    iki farklı hesap riski yok.

    Faz 312 — kullanıcı isteği: Bollinger Bandı ve Fibonacci retracement
    başlangıçta planlanan ama unutulan iki yöntemdi — eklendi."""
    from market_data.features.price_structure import compute_support_resistance_zones
    from market_data.features.signal_engine import (
        compute_bollinger_band_levels,
        compute_donchian_channels,
        compute_fibonacci_price_levels,
        compute_keltner_channels,
        compute_pivot_points,
        compute_volume_profile,
    )

    levels: dict[str, float] = {}

    sr = compute_support_resistance_zones(hourly_data)
    if sr["resistance_zones"]:
        levels["sr_resistance"] = min(
            sr["resistance_zones"], key=lambda z: abs(z["level"] - current_price)
        )["level"]
    if sr["support_zones"]:
        levels["sr_support"] = min(
            sr["support_zones"], key=lambda z: abs(z["level"] - current_price)
        )["level"]

    vp = compute_volume_profile(hourly_data)
    if vp["poc_price"] is not None:
        levels["volume_profile_poc"] = vp["poc_price"]
    if vp["value_area_high"] is not None:
        levels["volume_profile_va_high"] = vp["value_area_high"]
    if vp["value_area_low"] is not None:
        levels["volume_profile_va_low"] = vp["value_area_low"]

    pivots = compute_pivot_points(daily_data) if daily_data else None
    if pivots is not None:
        levels["pivot_r1"] = pivots["pivot_classic"]["R1"]
        levels["pivot_s1"] = pivots["pivot_classic"]["S1"]

    donchian = compute_donchian_channels(hourly_data)
    if donchian is not None:
        levels["donchian_upper"] = donchian["donchian_upper"]
        levels["donchian_lower"] = donchian["donchian_lower"]

    keltner = compute_keltner_channels(hourly_data)
    if keltner is not None:
        levels["keltner_upper"] = keltner["keltner_upper"]
        levels["keltner_lower"] = keltner["keltner_lower"]

    bollinger = compute_bollinger_band_levels(hourly_data)
    if bollinger is not None:
        levels["bollinger_upper"] = bollinger["bollinger_upper"]
        levels["bollinger_lower"] = bollinger["bollinger_lower"]

    fibonacci = compute_fibonacci_price_levels(hourly_data)
    if fibonacci is not None:
        levels["fibonacci_nearest"] = fibonacci["fibonacci_nearest"]

    return levels


def snap_target_to_confluence(
    direction: str,
    current_price: float,
    target_price: float,
    zones: list[dict],
    tolerance_pct: float = 0.005,
    min_method_count: int = 2,
) -> tuple[float, dict | None]:
    """Faz 299 canlı bağlantısı — kullanıcı isteği (2026-08-19): "wire
    edelim." ATR-tabanlı hedef ile şu anki fiyat arasında GERÇEK bir
    confluence bölgesi (>=min_method_count bağımsız yöntem) varsa —
    yani fiyatın hedefe ulaşmadan ÖNCE gerçek bir direnç/destekle
    karşılaşacağı anlamına gelir — hedef o bölgenin hemen önüne
    çekiliyor (daha erken, daha gerçekçi kâr alımı). SADECE hedefi
    SIKILAŞTIRIR (mevcut ATR hedefinden DAHA UZAĞA asla taşımaz) —
    Kelly/CPPI/trailing stop ile AYNI "sadece küçültür" ilkesi. Uygun
    bir bölge yoksa (fail-closed) orijinal target_price aynen döner.

    Döner: (nihai_target_price, kullanılan_zone_ya_da_None)."""
    if current_price <= 0 or not zones:
        return target_price, None

    candidates = [
        z for z in zones
        if z["method_count"] >= min_method_count
        and (
            (direction == "LONG" and current_price < z["level"] < target_price)
            or (direction == "SHORT" and target_price < z["level"] < current_price)
        )
    ]
    if not candidates:
        return target_price, None

    # Fiyata en YAKIN (yani hedefe ulaşmadan İLK karşılaşılacak) bölge —
    # en muhafazakâr seçim, hedefi mümkün olan en erken gerçekçi noktaya çeker.
    nearest = min(candidates, key=lambda z: abs(z["level"] - current_price))
    buffer = tolerance_pct / 2  # bölgenin TAM üstüne değil, hemen önüne
    adjusted = nearest["level"] * (1 - buffer) if direction == "LONG" else nearest["level"] * (1 + buffer)
    return adjusted, nearest


def snap_stop_to_confluence(
    direction: str,
    current_price: float,
    stop_price: float,
    zones: list[dict],
    tolerance_pct: float = 0.005,
    min_method_count: int = 2,
) -> tuple[float, dict | None]:
    """Faz 317-sonrası — kullanıcı bulgusu: aynı 7-yöntemli confluence
    verisi (compute_price_levels) SADECE hedefe uygulanıyordu, stop'a hiç
    dokunmuyordu — "SL'de de faydalı olmaz mıydı o veri?" Gerçek trading
    pratiğiyle de örtüşüyor: stop, rastgele bir ATR mesafesi yerine
    GERÇEK bir desteğin/direncin hemen ÖTESİNE konmalı.

    ATR-tabanlı stop ile şu anki fiyat ARASINDA gerçek bir confluence
    bölgesi (>=min_method_count bağımsız yöntem) varsa — yani fiyatın
    stop'a ulaşmadan ÖNCE gerçek bir destek/dirençle karşılaşacağı
    anlamına gelir — stop o bölgenin hemen ötesine (fiyata daha YAKIN)
    çekilir.

    snap_target_to_confluence ile AYNI "sadece sıkılaştırır" garantisi —
    ama BURADA garanti YAPI GEREĞİ kesin: candidate zone'lar TANIM
    GEREĞİ fiyat İLE mevcut ATR-stop ARASINDA kaldığı için, seçilen
    zone ne olursa olsun sonuç asla mevcut ATR-stop'tan DAHA UZAĞA
    gidemez — riski ASLA artırmaz (Kelly/CPPI/breakeven ratchet ile
    AYNI ilke). Uygun bir bölge yoksa (fail-closed) orijinal stop_price
    aynen döner.

    Döner: (nihai_stop_price, kullanılan_zone_ya_da_None)."""
    if current_price <= 0 or not zones:
        return stop_price, None

    candidates = [
        z for z in zones
        if z["method_count"] >= min_method_count
        and (
            (direction == "LONG" and stop_price < z["level"] < current_price)
            or (direction == "SHORT" and current_price < z["level"] < stop_price)
        )
    ]
    if not candidates:
        return stop_price, None

    # Fiyata en YAKIN (yani stop'a ulaşmadan İLK karşılaşılacak) bölge —
    # stop'u mümkün olan en erken gerçekçi (fiyata en yakın, en sıkı)
    # noktaya çeker.
    nearest = min(candidates, key=lambda z: abs(z["level"] - current_price))
    buffer = tolerance_pct / 2  # bölgenin TAM üstüne değil, hemen ÖTESİNE (koruma payı)
    # Faz 368 — Hypothesis'in bulduğu gerçek bug: nearest["level"] adaylık
    # filtresiyle stop_price'a YAKIN olabilir (fiyat ile ATR-stop arasında
    # olma şartı sadece "kesinlikle içeride" der, "ne kadar içeride"
    # demez) — buffer bu durumda level'i stop_price'ın ÖTESİNE (ATR-
    # stop'tan bile daha uzağa) itebiliyordu, docstring'in "asla riski
    # artırmaz" garantisini bozuyordu. max/min ile stop_price'a kelepçe —
    # buffer HİÇBİR ZAMAN orijinal ATR-stop'u aşamaz.
    if direction == "LONG":
        adjusted = max(nearest["level"] * (1 - buffer), stop_price)
    else:
        adjusted = min(nearest["level"] * (1 + buffer), stop_price)
    return adjusted, nearest
