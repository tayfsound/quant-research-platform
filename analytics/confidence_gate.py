"""Minimum Confidence Kapısı — Faz 421 (2026-09-06). Kullanıcı isteği:
gerçek veriyle (confidence kovaları) LONG'da confidence≈0,7'nin hem
yüksek kazanma oranı (%85,2) HEM gerçek pozitif PnL (+$11,65/işlem,
n=1260) verdiği bulundu — 0,3/0,5/0,6 gibi kovalar yüksek kazanma
oranına rağmen derin PnL negatifiydi (aynı R:R skew imzası, confidence'tan
bağımsız). "Canlıda sadece 0,7 confidence bulduğunda değerlendirsin"
isteğiyle — confidence bu tabanın ALTINDAYSA pozisyon açılmıyor.

Not: kanıt SADECE LONG verisinden geldi (SHORT bu turda zaten
direction_trading_enabled ile kapalı) — SHORT yeniden açılırsa bu eşiğin
SHORT için de geçerli olup olmadığı AYRI bir soru, henüz doğrulanmadı."""


def is_confidence_trading_blocked(confidence: float | None, enabled: bool, min_confidence: float) -> bool:
    """True dönerse bu karar engellenmeli. confidence None/bilinmiyorsa
    hiç engellenmez (fail-open — diğer kullanıcı-tercihi kapılarıyla
    AYNI ilke, bkz. regime_trading_gate.py). Kapı kapalıysa (enabled=
    False) da hiç engellenmez."""
    if not enabled or confidence is None:
        return False
    return confidence < min_confidence
