"""Faz 361 — rejime göre piramitleme kapısı, saf (pure) hesaplama katmanı.

Kullanıcı bulgusu (2026-08-24): "aynı sembol/yönde açık pozisyon varken
daha kötü fiyattan üste eklemek" (piramitleme + tepeden giriş) tüm-zamanlar
toplamında zararlı görünmüyordu (worse-price add win_rate %64.3, better-price
add'ten bile yüksek) — ama bu, tarihin çoğunun lehte/trend rejiminde
geçmesinden kaynaklanıyordu. Rejime (market_regime = "{trend}_{volatility}",
bkz. services/position_closer.py::_extract_market_regime ile AYNI format)
göre kırılınca gerçek tablo ortaya çıktı: SADECE "bullish_low" rejiminde
worse-price add gerçekten en iyi seçenek (n=355, %76 — fresh giriş %63 ve
better-price add %65'ten bile yüksek). Diğer TÜM rejimlerde (bullish_normal
%53, bullish_high %44, bearish_low %42, bearish_normal %35, bearish_high
%28, unknown %30) worse-price add ya fresh girişten kötü ya da en kötü
seçenek. Kullanıcının kararı: "sadece en yüksek performans gösterdiği
rejimde bunu yapmasına izin verelim, onun dışında kesin olarak yasaklayalım"
— matematiksel olarak kârı maksimize, zararı minimize eden tek seçim.

Fail-closed: rejim bilinmiyorsa (None/"unknown") ya da beklenen formatta
değilse, izin verilen rejimle EŞLEŞMEZ — yani worse-price add ENGELLENİR."""

ALLOWED_WORSE_PRICE_REGIME_DEFAULT = "bullish_low"


def is_worse_price_pyramid_blocked(
    direction: str,
    entry_price: float,
    existing_avg_entry_price: float | None,
    market_regime: str | None,
    allowed_regime: str = ALLOWED_WORSE_PRICE_REGIME_DEFAULT,
) -> bool:
    """True dönerse bu giriş (mevcut aynı sembol/yön pozisyonlarına göre
    daha kötü fiyattan bir piramitleme) engellenmeli. existing_avg_entry_
    price None ise (bu sembol/yönde hiç açık pozisyon yok — piramitleme
    değil, ilk giriş) her zaman False — bu kapı SADECE piramitleme
    durumunu hedefliyor."""
    if existing_avg_entry_price is None:
        return False

    direction = (direction or "").upper()
    if direction == "LONG":
        is_worse_price = entry_price > existing_avg_entry_price
    elif direction == "SHORT":
        is_worse_price = entry_price < existing_avg_entry_price
    else:
        return False

    if not is_worse_price:
        return False

    return market_regime != allowed_regime
