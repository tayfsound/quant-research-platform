"""Yön (LONG/SHORT) Aç/Kapa Kapısı — kullanıcı isteği (2026-08-28):
Dashboard'daki "LONG kazanma oranı"/"SHORT kazanma oranı" kartlarına manuel
bir aç/kapa anahtarı — SADECE kullanıcı kararı, modelin/analizin otomatik
kısıtlaması DEĞİL (kullanıcı açıkça: "short işlemlerini kısıtlamayalım, ben
gerekli görürsem dashboard'dan kapatırım" — Grok raporunun SHORT'u varsayılan
kapat/daralt önerisi burada BİLEREK uygulanmıyor). regime_trading_gate.py/
asset_class_trading_gate.py ile AYNI basit, fail-open desen — yeni bir
sınıflandırıcı yok, sadece "direction" alanı."""


def is_direction_trading_blocked(direction: str | None, enabled_map: dict) -> bool:
    """True dönerse bu yönde (LONG/SHORT) yeni giriş engellenmeli.
    direction None/bilinmiyorsa hiç engellenmez. enabled_map'te hiç kaydı
    olmayan bir yön varsayılan AÇIK sayılır (fail-open — bu bir kullanıcı
    tercihi kapısı, güvenlik kapısı değil)."""
    if direction is None:
        return False
    return enabled_map.get(direction, True) is False
