"""SHORT Sadece-Scalp Kapısı — Faz 426 (2026-09-07). Kullanıcı isteği:
"scalp only kapı ayarlayalım." Faz 425'in gerçek MAE/MFE ızgara
taramasının bulduğu şey: scalp-mesafeli SHORT'ta (gerçek stop%<%4,5)
gerçek/pozitif bir kenar var, swing-mesafeli SHORT'ta (stop%>=%4,5)
ise ızgaradaki HİÇBİR stop/hedef çifti pozitif EV vermiyor (Faz 320'nin
bağımsız doğrulaması). `target_atr_mult_short` TEK global bir çarpan
olduğu için (scalp/swing'i önceden ayırt eden ayrı bir mekanizma yok)
SHORT'u tekrar `direction_trading_enabled` ile açmak swing-mesafeli
SHORT'u da geri getirir — bu kapı, o boşluğu kapatıyor: pozisyon gerçek
stop mesafesine göre swing olarak sınıflanıyorsa SHORT engellenir, scalp
ise geçer. LONG hiç etkilenmez.

regime_trading_gate.py/confidence_gate.py ile AYNI fail-open desen —
trade_type hesaplanamıyorsa (entry/stop fiyatı yok) hiç engellenmez."""


def is_short_swing_blocked(direction: str | None, trade_type: str | None, enabled: bool) -> bool:
    """True dönerse bu karar engellenmeli. Sadece direction=="SHORT" VE
    trade_type=="swing" iken devreye girer — LONG'a hiç dokunmaz, scalp
    SHORT'u hiç engellemez, trade_type None/bilinmiyorsa (entry_price/
    stop_loss_price henüz hesaplanmamışsa) hiç engellenmez (fail-open)."""
    if not enabled or direction != "SHORT" or trade_type is None:
        return False
    return trade_type != "scalp"
