"""Pivotal Agent Sizing Gate — Faz 368, kullanıcı bulgusu (Grok raporu
doğrulaması, agent_ablation.py'nin GERÇEK karşı-olgusal verisi): technical
ajanı pivot olduğunda (yani technical'ın oyu OLMASAYDI bu karar hiç
açılmaz/farklı yöne açılırdı) kazanma oranı %25.4 (n=63) — genel ortalama
(~%74) baseline'ın çok altında. Aynı ölçümde order_flow (%98, n=50) ve
macro (%91.8, n=572) pivot olduklarında TAM TERSİNE çok güçlüler.

Kasıtlı olarak "technical" adını hardcode ETMİYOR — analytics/agent_
ablation.py'nin haftalık raporundan HANGİ domain'in pivot-olunca-kötü
olduğunu okuyup, O ANKİ kararda GERÇEKTEN pivot olan (agent_ablation.py::
synthesize_with_domain_excluded ile CANLI test edilen — kararın oyu
sıfırlansa yön değişir miydi) domain'ler için boyutu küçültür. Bugün
technical kötü çıkıyor, yarın veri değişirse otomatik başka bir domain'e
kayar — sabit bir "ajan X'e güvenme" kuralı icat edilmiyor.

risk/drawdown_sizing.py ve diğer sizing gate'lerle AYNI 'asla büyütmez,
sadece küçültür' ailesi."""

MIN_SAMPLES_FOR_TRUST = 10
MIN_MULTIPLIER = 0.4


def identify_risky_pivotal_domains(
    by_domain: dict, baseline_win_rate: float, min_samples: int = MIN_SAMPLES_FOR_TRUST,
) -> dict[str, float]:
    """agent_ablation raporunun by_domain'inden, pivot olunca (caused_
    trade) kazanma oranı baseline'ın ALTINDA kalan VE yeterli örneklemi
    olan domain'leri {domain: caused_trade_win_rate} olarak döner.
    Yeterli örneklemi olmayan (min_samples altı) ya da hiç pivot olmamış
    (caused_trade_win_rate=None) bir domain asla riskli sayılmaz — fail-
    open, icat edilmiş bir yargı üretilmez."""
    risky: dict[str, float] = {}
    for domain, stats in (by_domain or {}).items():
        win_rate = stats.get("caused_trade_win_rate")
        count = stats.get("caused_trade_count") or 0
        if win_rate is None or count < min_samples:
            continue
        if win_rate < baseline_win_rate:
            risky[domain] = win_rate
    return risky


def pivotal_domain_size_multiplier(caused_trade_win_rate: float, baseline_win_rate: float) -> float:
    """caused_trade_win_rate/baseline_win_rate oranı — analytics/self_
    correction_sizing_gate.py ile AYNI orantılı desen (icat edilmiş bir
    eğri değil). [MIN_MULTIPLIER, 1.0] aralığında sabitlenir, asla
    büyütmez (oran >1.0 çıksa bile — bu domain zaten 'riskli' listesine
    girmeden önce baseline'ın altında olduğu için pratikte hep <1.0)."""
    if baseline_win_rate <= 0:
        return 1.0
    ratio = caused_trade_win_rate / baseline_win_rate
    return max(MIN_MULTIPLIER, min(1.0, ratio))
