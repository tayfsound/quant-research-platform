"""Faz 337 — Execution Impact Estimator. Kullanıcı onayı: "ExecutionAgent
alpha üretmesin, sadece 'bu kararı piyasada nasıl en az hasarla
gerçekleştiririm' sorusuna cevap versin." Bu yüzden bilinçli olarak bir
AgentDomain/oy-veren ajan DEĞİL — saf bir tahmin fonksiyonu, gerçek karar
büyüklüğünü/yönünü hiç DEĞİŞTİRMİYOR (v1: sadece ÖLÇÜP KAYDEDİYOR, bkz.
modül sonundaki not).

Gerçek veri kısıtı: order_book_snapshots tablosu (Faz 186) tam derinlik
(çoklu seviye bid/ask) SAKLAMIYOR — sadece en iyi fiyat + o seviyedeki
hacim + spread. Bu yüzden klasik "defteri yürüyerek" (walk-the-book)
slippage hesabı yapılamıyor. Bunun yerine literatürde standart, iyi
belgelenmiş bir yaklaşıklama kullanılıyor: piyasa etkisinin "kare-kök
yasası" (square-root law of market impact — Kyle 1985, Almgren-Chriss
2000, sayısız ampirik çalışmada doğrulanmış): etki ~ sqrt(emir
büyüklüğü / mevcut likidite). İcat edilmiş bir katsayı değil, bu alanın
standart fonksiyonel formu."""

# Faz 186'nın en-iyi-seviye hacminin ötesine geçen bir emrin GERÇEK
# derinlik dağılımını bilmiyoruz — bu yüzden kare-kök modelinin
# katsayısı 1.0 (yaklaşıklamanın kendisi zaten muhafazakar/aşırı tahmin
# etme eğiliminde, "en iyisini varsay" değil "en kötüsünü varsay" yönünde
# hata payı bırakılıyor).
_IMPACT_COEFFICIENT = 1.0


def estimate_execution_cost_pct(order_book: dict, notional_usd: float, direction: str) -> dict | None:
    """order_book: MarketDataRepository.get_latest_order_book_snapshot()'ın
    döndürdüğü satır (best_bid/best_ask/bid_volume/ask_volume/spread_bps
    alanları). notional_usd: açılacak pozisyonun $ büyüklüğü (marjin×
    kaldıraç). direction: 'LONG' (ask tarafından alım) ya da 'SHORT' (bid
    tarafından satım).

    Döner: {'spread_cost_pct', 'impact_cost_pct', 'total_cost_pct',
    'depth_ratio'} — ya da veri eksikse/dejenereyse (best_bid<=0 vb.)
    fail-closed None (icat edilmiş bir maliyet asla üretilmez)."""
    if not order_book or notional_usd <= 0:
        return None

    best_bid = order_book.get("best_bid")
    best_ask = order_book.get("best_ask")
    spread_bps = order_book.get("spread_bps")
    volume = order_book.get("ask_volume") if direction == "LONG" else order_book.get("bid_volume")
    price = best_ask if direction == "LONG" else best_bid

    if not price or price <= 0 or not volume or volume <= 0 or spread_bps is None:
        return None

    spread_cost_pct = (spread_bps / 2.0) / 10000.0

    available_liquidity_usd = price * volume
    depth_ratio = notional_usd / available_liquidity_usd
    impact_cost_pct = spread_cost_pct * _IMPACT_COEFFICIENT * (depth_ratio ** 0.5)

    return {
        "spread_cost_pct": round(spread_cost_pct, 6),
        "impact_cost_pct": round(impact_cost_pct, 6),
        "total_cost_pct": round(spread_cost_pct + impact_cost_pct, 6),
        "depth_ratio": round(depth_ratio, 4),
    }


# Faz 337 kapsamı — kullanıcı onaylı, kasıtlı sınır: bu fonksiyonun
# çıktısı şu an SADECE decision_recorder.py/pump_fade_strategy.py'de
# agent_contributions'a bir "execution_cost_estimate" kaydı olarak
# YAZILIYOR (bkz. o dosyalardaki Faz 337 notları) — final_size/quantity'yi
# HİÇ etkilemiyor. "Yeni execution-cost modeli = ölçüm/simülasyon,
# hemen güvenli; ama GERÇEK KARARA (boyut küçültme) bağlamak = ayrı,
# açık bir onay gerektirir" ilkesi (kullanıcı + harici AI incelemesi
# ortak kararı) — gerçek ölçülen maliyetlerin ne kadar büyük/anlamlı
# olduğu birkaç hafta gözlemlenmeden otomatik bir gate eklenmiyor.
