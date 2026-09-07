"""Forward Direction Etiketleme — Faz 441 (2026-09-07). Bkz.
/Users/emreturkes/.claude/plans/velvety-whistling-parasol.md.

Bağlam: kullanıcı + GPT teşhisi — sistem şu an ÖRTÜK olarak "bu durumda
açılan işlem geçmişte para kazandı mı" (trade outcome — stop/target
yerleşimine, tutma süresine bağlı) öğreniyor, ama asıl soru "bu
entry'den sonra fiyat hangi yöne gitti" (direction — sabit bir ufukta,
trade'in kendi bariyer tasarımından TAMAMEN bağımsız). Bu iki hedef AYNI
DEĞİL — bir LONG %1,5 düşüp sonra %4 yükselip TP'ye ulaşabilir (trade
kazandı) ama entry anındaki yön tahmini kısa vadede yanlıştı.

`analytics/mae_mfe.py`/`barrier_table_builder.py` (SL/TP yerleşimi
optimizasyonu, competing-risks) İLE KARIŞTIRILMAMALI — o modüller "bu
bariyerlerle ne olurdu" sorusuna cevap veriyor, bu modül bariyer YOK
SAYILDIĞINDA (sabit bir zaman ufkunda) fiyatın nereye gittiğine.

Kasıtlı olarak SADECE etiketleme — hiçbir canlı kararı etkilemiyor."""

DEFAULT_THRESHOLD_PCT = 0.0005  # %0.05 — sabit, oynaklığa göre normalize EDİLMEDİ (bkz. modül notu)


def label_forward_direction(
    entry_price: float, price_at_horizon: float, threshold_pct: float = DEFAULT_THRESHOLD_PCT,
) -> str | None:
    """entry_price: karar anındaki fiyat. price_at_horizon: SABİT bir
    zaman ufku sonraki (ör. 1 saat), trade'in KENDİ stop/target/tutma
    süresinden TAMAMEN bağımsız gerçek piyasa fiyatı. forward_return =
    (price_at_horizon - entry_price) / entry_price; > threshold_pct ise
    "UP", < -threshold_pct ise "DOWN", aksi halde "NEUTRAL" (fiyat kısa
    vadede anlamsız küçük bir hareket yapmış — GPT'nin uyarısı: buna
    zorla LONG/SHORT etiketi vermek modele gereksiz gürültü öğretir).

    threshold_pct SABİT bir yüzde — GPT'nin önerisi (oynaklığa/ATR'ye göre
    normalize edilmiş bir eşik) BİLİNÇLİ olarak bu ilk fazda uygulanmadı,
    dürüstçe belirtiliyor (bkz. plan dosyası) — Faz 437'nin
    `atr_expansion_ratio`'su ileride bunun için kullanılabilir.

    entry_price<=0 ise (dejenere/eksik veri) None — icat edilmiş bir
    etiket asla üretilmez."""
    if entry_price is None or price_at_horizon is None or entry_price <= 0:
        return None
    forward_return = (price_at_horizon - entry_price) / entry_price
    if forward_return > threshold_pct:
        return "UP"
    if forward_return < -threshold_pct:
        return "DOWN"
    return "NEUTRAL"
