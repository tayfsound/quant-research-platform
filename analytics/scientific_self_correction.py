"""Active Research Intelligence + Scientific Self-Correction — Faz 1061-1100
(Cognitive Core 8.0-9.0).

experiments tablosu (curiosity_id/hypothesis/test_expression) zaten bir
hipotez-test çerçevesi tutuyor ama hiçbir RETEST/geçersizleştirme
mekanizması yoktu — bir hipotez bir kez doğrulanınca sonsuza kadar
"doğru" kabul ediliyordu, piyasa rejimi değişip edge kaybolsa bile. Bu
modül, standart bir iki-oran z-testi (two-proportion z-test) ile bir
hipotezin ORİJİNAL doğrulanma sonucunun GÜNCEL veriyle hâlâ geçerli olup
olmadığını test ediyor — "bilimsel öz-düzeltme": edge kaybolduysa bunu
DÜRÜSTÇE tespit edip hipotezi geçersiz kılıyor, savunmuyor. İcat edilmiş
bir eşik değil.

Kasıtlı olarak SADECE değerlendirme/rapor — hiçbir hipotezi/stratejiyi
burada otomatik silmiyor/uygulamıyor."""
import math

from scipy import stats

MIN_SAMPLE_SIZE = 20
SIGNIFICANCE_LEVEL = 0.05


def compute_hypothesis_retest(
    original_wins: int,
    original_n: int,
    recent_wins: int,
    recent_n: int,
) -> dict | None:
    """original_wins/original_n: hipotezin İLK doğrulandığı zamanki
    GERÇEK win/toplam sayısı. recent_wins/recent_n: GÜNCEL, taze veriyle
    aynı hipotezin retest sonucu. İki-oran z-testiyle fark anlamlı mı
    kontrol edilir. hypothesis_still_valid: fark anlamlı DEĞİLSE, ya da
    anlamlıysa ve win_rate DÜŞMEDİYSE (edge kaybolmadıysa/güçlendiyse)
    True. <MIN_SAMPLE_SIZE her iki grupta da olmalı, sıfır varyanslı
    (p_pooled 0 ya da 1) dejenere durumda fail-closed None döner."""
    if original_n < MIN_SAMPLE_SIZE or recent_n < MIN_SAMPLE_SIZE:
        return None

    p1 = original_wins / original_n
    p2 = recent_wins / recent_n
    p_pooled = (original_wins + recent_wins) / (original_n + recent_n)
    se = math.sqrt(p_pooled * (1 - p_pooled) * (1 / original_n + 1 / recent_n))
    if se == 0:
        return None

    z = (p1 - p2) / se
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    significant_change = p_value < SIGNIFICANCE_LEVEL
    hypothesis_still_valid = (not significant_change) or (p2 >= p1)

    return {
        "original_win_rate": round(p1, 4),
        "recent_win_rate": round(p2, 4),
        "p_value": round(float(p_value), 6),
        "significant_change": bool(significant_change),
        "hypothesis_still_valid": bool(hypothesis_still_valid),
        "original_sample_size": original_n,
        "recent_sample_size": recent_n,
    }
