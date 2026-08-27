"""Varlık Sınıfı Aç/Kapa Kapısı — kullanıcı isteği (2026-08-27):
"Emtia, Token ve Hisse Senedi'ni Settings'te aç kapa yapabileceğimiz
modüller yazabilir miyiz?" services/agent_memory.py::asset_class_
trading_category() TEK kaynak (crypto/commodity/equity) — burada
YENİDEN sınıflandırma yapılmıyor, sadece o kategorinin açık/kapalı
olup olmadığına bakılıyor."""


def is_asset_class_trading_blocked(category: str | None, enabled_map: dict) -> bool:
    """True dönerse bu varlık sınıfında yeni giriş engellenmeli.
    category None ise (asset_class_trading_category() "other" döndüyse
    — hiçbir tanımlı sınıfa girmeyen bir sembol) hiç engellenmez, bu
    kapının kapsamı dışında. enabled_map'te hiç kaydı olmayan bir
    kategori varsayılan olarak AÇIK sayılır — yeni bir kategori
    eklendiğinde sessizce her şeyi durdurmasın diye (fail-open, bu
    diğer risk kapılarının fail-closed disiplininden BİLİNÇLİ farklı —
    burası bir güvenlik kapısı değil, kullanıcı tercihi)."""
    if category is None:
        return False
    return enabled_map.get(category, True) is False
