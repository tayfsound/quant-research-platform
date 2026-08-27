"""Direction × Regime Asymmetry — Faz 364-devam, kullanıcı hipotezi:
"bir rejimde SHORT başarısızsa, aynı rejimde LONG başarılı mı — rejimler
arasında yön-bazlı bir ters ilişki var mı?" (bearish_low: SHORT swing
%5.4 vs LONG swing %85.9/LONG scalp %96.5 — çarpıcı bir örnek zaten
bulundu, bu modül bunu TÜM rejimler/stratejiler için sistematik hale
getiriyor).

Yeni bir DB sorgusu YAZILMADI: analytics/strategy_regime_compatibility.py
zaten her strateji×yön×trade_type etiketini (ör. "ai_council_SHORT_swing")
rejime kırıyor — bu saf fonksiyon SADECE o çıktıyı LONG/SHORT çiftleri
halinde eşleştirip ortak rejimlerde win_rate farkını hesaplıyor.
Kasıtlı olarak SADECE ölçüm/rapor — hiçbir gate'e bağlı değil."""
import re

_LABEL_RE = re.compile(r"^(.*)_(LONG|SHORT)(_.*)?$")


def compute_direction_regime_asymmetry(by_strategy: dict) -> dict:
    """by_strategy: strategy_regime_compatibility_gatherer'ın (ya da
    compute_strategy_regime_compatibility'nin) çıktısı — {label: {
    'overall_win_rate', 'overall_sample_size', 'by_regime': {...}}}.

    Aynı taban+trade_type'a sahip LONG/SHORT etiketlerini eşleştirip
    (ör. "ai_council_LONG_swing" <-> "ai_council_SHORT_swing") ortak
    rejimlerde win_rate farkını (LONG - SHORT) döner. Sadece bir yönü
    olan etiketler (ör. basis_arb_v1'in tek taraflı kalıntıları)
    kasıtlı olarak dışlanır — eşleşme yoksa karşılaştırma anlamsız."""
    sides: dict[str, dict[str, dict]] = {}
    for label, data in by_strategy.items():
        match = _LABEL_RE.match(label)
        if not match:
            continue
        base = match.group(1) + (match.group(3) or "")
        direction = match.group(2)
        sides.setdefault(base, {})[direction] = data

    result: dict = {}
    for base, pair in sides.items():
        if "LONG" not in pair or "SHORT" not in pair:
            continue
        long_regimes = pair["LONG"]["by_regime"]
        short_regimes = pair["SHORT"]["by_regime"]
        shared_regimes = set(long_regimes) & set(short_regimes)
        if not shared_regimes:
            continue

        by_regime = {}
        for regime in shared_regimes:
            long_cell = long_regimes[regime]
            short_cell = short_regimes[regime]
            by_regime[regime] = {
                "long_win_rate": long_cell["win_rate"],
                "long_sample_size": long_cell["sample_size"],
                "short_win_rate": short_cell["win_rate"],
                "short_sample_size": short_cell["sample_size"],
                "delta_long_minus_short": round(long_cell["win_rate"] - short_cell["win_rate"], 4),
            }

        result[base] = {
            "long_overall_win_rate": pair["LONG"]["overall_win_rate"],
            "short_overall_win_rate": pair["SHORT"]["overall_win_rate"],
            "by_regime": by_regime,
        }

    return result
