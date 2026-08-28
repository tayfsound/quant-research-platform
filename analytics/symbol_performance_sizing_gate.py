"""Symbol Performance Sizing Gate — Faz 368, kullanıcı bulgusu (Grok
raporu doğrulaması): council SL zararları belirli sembol×yön hücrelerinde
sistematik olarak yoğunlaşıyor — ATOMUSDT_LONG (n=41, %31.7 kazanma,
-$38.2k), ALGOUSDT_LONG (n=14, %42.9, -$14.2k), AVAXUSDT_LONG (n=30,
%40.0, -$13.6k), XLMUSDT_LONG (n=19, %26.3, -$13.1k), ARBUSDT_LONG (n=31,
%48.4, -$12.4k) — hepsi genel baseline'ın (~%74) ÇOK altında.

analytics/pivotal_agent_sizing_gate.py ve analytics/self_correction_
sizing_gate.py ile AYNI orantılı 'asla büyütmez, sadece küçültür' aile —
kullanıcı kararı (2026-08-28, LONG/SHORT anahtarında da AYNI tercih):
kara liste/tam engelleme DEĞİL, boyut küçültme. Belirli bir semboldeki
kötü performans piyasa geneli değişince (yeni veri biriktikçe) kendini
düzeltebilir — sabit bir 'bu sembolü asla açma' kuralı icat edilmiyor."""

MIN_SAMPLES_FOR_TRUST = 10
MIN_MULTIPLIER = 0.4


def symbol_direction_size_multiplier(
    win_rate: float | None, sample_size: int | None, baseline_win_rate: float,
) -> float:
    """win_rate/sample_size: gather_symbol_direction_performance()'ın
    ilgili sembol×yön kaydı. Yeterli örneklemi olmayan (min_samples altı)
    ya da hiç veri olmayan bir sembol asla küçültülmez — fail-open, icat
    edilmiş bir yargı üretilmez. win_rate baseline'ın ÜSTÜNDEYSE ya da
    eşitse tam boyut. Aksi halde win_rate/baseline oranı [MIN_MULTIPLIER,
    1.0] aralığında sabitlenir (self_correction_sizing_gate.py ile AYNI
    desen)."""
    if win_rate is None or sample_size is None or sample_size < MIN_SAMPLES_FOR_TRUST:
        return 1.0
    if baseline_win_rate <= 0 or win_rate >= baseline_win_rate:
        return 1.0
    ratio = win_rate / baseline_win_rate
    return max(MIN_MULTIPLIER, ratio)
