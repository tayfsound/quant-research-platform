"""Faz 268-sonrası: Drawdown-Based Position Sizing (gambler's ruin koruması).

Gerçek olay (2026-08-12): Kelly (services/kelly_sizing.py) ve CPPI
(risk/predictive/cppi.py) pozisyon BÜYÜKLÜĞÜNÜ optimize ediyordu, ama bir
seri kayıp sırasında kademeli bir koruma yoktu — sadece kill switch'in
SERT eşiği (engines/risk_engine.py, varsayılan 10 ardışık kayıp) vardı.
Gerçek 50 ardışık kayıp olayında sistem tam boyutla işlem açmaya devam
etti, ta ki kill switch nihayet devreye girene kadar. Bu modül, kill
switch'in KULLANDIĞI AYNI gerçek ardışık kayıp sayacını (services/
risk_state.py — tek gerçek veri kaynağı, iki ayrı hesaplama yok) erken
bir uyarı sinyali olarak kullanıp, eşiğe yaklaşıldıkça boyutu kademeli
küçültüyor — kill switch'in "hep ya da hiç" sert durmasından ÖNCE devreye
giren yumuşak bir fren."""

MIN_MULTIPLIER = 0.25


def drawdown_size_multiplier(
    consecutive_losses: int,
    start_after_losses: int,
    full_reduction_at_losses: int,
) -> float:
    """start_after_losses'a kadar tam boyut (1.0, mevcut Kelly/CPPI
    çıktısı hiç değişmez). start_after_losses'tan full_reduction_at_
    losses'a kadar [1.0, MIN_MULTIPLIER] aralığında DOĞRUSAL küçülür —
    icat edilmiş bir eğri değil, en basit/açıklanabilir orantı (CPPI'nin
    zaten kullandığı desenle aynı). full_reduction_at_losses'tan sonra
    MIN_MULTIPLIER'da sabit kalır — kill switch (varsa) zaten normal
    yapılandırmada bundan önce devreye girmiş olur, ama bu fonksiyon kill
    switch'in açık/kapalı olmasından TAMAMEN bağımsız, kendi başına
    güvenli (asla sıfıra ya da negatife düşmez)."""
    if consecutive_losses < start_after_losses:
        return 1.0
    if full_reduction_at_losses <= start_after_losses:
        return MIN_MULTIPLIER

    progress = (consecutive_losses - start_after_losses) / (full_reduction_at_losses - start_after_losses)
    progress = min(max(progress, 0.0), 1.0)
    return max(MIN_MULTIPLIER, 1.0 - progress * (1.0 - MIN_MULTIPLIER))
