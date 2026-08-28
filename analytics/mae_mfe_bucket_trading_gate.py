"""MAE/MFE Kova Aç/Kapa Kapısı — Faz 367-devam, kullanıcı isteği
(2026-08-28): canlıya kademeli geçiş için, dünkü Varlık Sınıfı/Rejim
aç-kapa kapılarından DAHA GRANÜLER bir kontrol katmanı — kova anahtarı
analytics/mae_mfe.py'nin ürettiği (direction|regime|volatility_regime)
etiketiyle BİREBİR aynı (regime_trading_gate.py'nin market_regime'inden
FARKLI bir sınıflandırıcı, bkz. o modülün kendi notu — burada bilinçli
olarak icat edilmiyor, sadece MAE/MFE'nin zaten ürettiği etiket
yeniden kullanılıyor)."""


def is_mae_mfe_bucket_trading_blocked(bucket_key: str | None, enabled_map: dict) -> bool:
    """True dönerse bu (direction|regime|volatility_regime) kovasında
    yeni giriş engellenmeli. bucket_key None/bilinmiyorsa hiç engellenmez
    (regime_trading_gate.py ile AYNI ilke). enabled_map'te hiç kaydı
    olmayan bir kova varsayılan AÇIK sayılır (fail-open — bu bir kullanıcı
    tercihi kapısı, güvenlik kapısı değil; ayrıca kova sayısı zamanla
    değişebildiği için TÜM kovaları önceden numaralandırmaya gerek yok)."""
    if bucket_key is None:
        return False
    return enabled_map.get(bucket_key, True) is False


def build_bucket_key(direction: str, regime: str, volatility_regime: str, asset_class: str = "unknown") -> str:
    """analytics/mae_mfe.py::compute_conditional_mae_distribution'ın
    ürettiği etiketle (barrier_table_repository.py::GROUP_BY sırasıyla)
    BİREBİR aynı formatı üretir — dashboard'daki "Kova" sütunundaki
    metin doğrudan ayar anahtarı olsun diye, ayrı bir eşleme/çeviri
    katmanı icat edilmiyor.

    Faz 368 — GROUP_BY'a asset_class eklendi (bkz. barrier_table_
    repository.py'deki not); varsayılan="unknown" eski çağrı yerlerinin
    (varsa) kırılmaması için, ama tek gerçek çağıran (decision_recorder.py)
    bunu her zaman açıkça geçiyor."""
    from analytics.barrier_table_repository import GROUP_BY

    values = {
        "direction": direction,
        "regime": regime,
        "volatility_regime": volatility_regime,
        "asset_class": asset_class,
    }
    return "|".join(f"{field}={values[field]}" for field in GROUP_BY)
