"""Self-Model Sizing Gate — Faz 368, kullanıcı bulgusu (2026-08-28):
"Kill Switch aktif olduğu halde self control kapalı gibi görünüyor."
Kök neden: analytics/self_model.py::compute_self_reliability_snapshot()'ın
ürettiği overall_reliability ("high"/"degraded"/"untrustworthy") hiçbir
yerde trading kararına bağlı değildi — sadece dashboard'da gösteriliyordu.
Gerçek (sert, ikili) kill switch zaten ayrı ve çalışıyor (engines/
risk_engine.py::_trip_kill_switch — 10 ardışık kayıpta ai_enabled=false
yapıyor). Bu modül, Self-Model'in DAHA YUMUŞAK/erken "degraded" sinyalini
(feature drift, kötü kalibrasyon, düşük DSR — henüz kill switch'i
tetiklemeyen ama güveni zaten azaltan durumlar) pozisyon boyutuna bağlıyor
— risk/drawdown_sizing.py ve analytics/self_correction_sizing_gate.py ile
AYNI 'asla büyütmez, sadece küçültür' ailesi, sabit/açıklanabilir
çarpanlar (icat edilmiş bir eğri değil)."""

DEGRADED_MULTIPLIER = 0.7
UNTRUSTWORTHY_MULTIPLIER = 0.4


def self_model_size_multiplier(overall_reliability: str | None) -> float:
    """overall_reliability: SelfModelReportRepository'nin en son kaydettiği
    anlık görüntüdeki 'result.overall_reliability' alanı. 'untrustworthy'
    (kill switch aktif VEYA DSR çok düşük) en sert küçültmeyi, 'degraded'
    (drift/kalibrasyon gibi daha hafif bayraklar) orta küçültmeyi alır.
    'high' ya da bilinmeyen/eksik bir değer (henüz hiç anlık görüntü
    alınmamışsa) fail-open tam boyut döner — icat edilmiş bir küçültme
    asla uygulanmaz."""
    if overall_reliability == "untrustworthy":
        return UNTRUSTWORTHY_MULTIPLIER
    if overall_reliability == "degraded":
        return DEGRADED_MULTIPLIER
    return 1.0
