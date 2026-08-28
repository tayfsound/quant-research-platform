"""Feature Relationship — Faz 368. Feature Intelligence Layer'ın Faz A'sı.

Bağlam: analytics/feature_ic.py her feature'ı TEK BAŞINA, sadece getiriye
karşı ölçüyor. Ama bu turda gerçek veriyle (3648 kapanmış karar) doğrulandı:
trend/ema_alignment/momentum/vwap_confirm/adx_strong_confirm feature'ları
birbirleriyle r=1.000 (yüzlerce/binlerce işlem boyunca sapmasız) — yani
council'e 5 ayrı oy gibi giriyorlar ama matematiksel olarak TEK bir ikili
sinyalin 5 farklı ismi. Bu modül bu çakışmayı GÖRÜNÜR kılıyor:

1. compute_feature_redundancy: her feature ÇİFTİNİN birbiriyle (getiriyle
   değil, BİRBİRİYLE) korelasyonu.
2. compute_conditional_ic: yüksek-redundant çiftler için, "b zaten
   biliniyorken a'nın getiriye kattığı EK bilgi ne kadar" (kapalı-form
   2-değişkenli kısmi korelasyon).

Kasıtlı olarak SADECE ölçüm/raporlama — feature_ic.py'nin kendi ilkesiyle
AYNI: hiçbir ajanın skorlamasını otomatik değiştirmiyor, karar hattına
bağlanmıyor. Faz A kasıtlı olarak SADECE ikili (pairwise) — 3+ değişkenli
residualizasyon (kombinasyon patlaması riski) Faz B'ye bırakıldı."""
from collections import defaultdict
from itertools import combinations

from scipy import stats

MIN_SAMPLE_SIZE = 20
DEFAULT_REDUNDANCY_THRESHOLD = 0.7


def _collect_feature_samples(closed_trades: list[dict]) -> list[dict[str, float]]:
    """Her kapanmış trade için {feature_name: contribution} — feature_ic.py
    ::compute_feature_ic ile AYNI çıkarma mantığı (agent_contributions[].
    feature_contributions), ama getiriyle eşleştirmek yerine AYNI trade
    içindeki feature'ları birbiriyle hizalı tutmak için trade bazlı satır
    olarak döner (redundancy bir feature'ı BAŞKA bir feature'a karşı
    ölçüyor, getiriye karşı değil)."""
    per_trade: list[dict[str, float]] = []
    for trade in closed_trades:
        entry_price = trade.get("entry_price")
        exit_price = trade.get("exit_price")
        if not entry_price or exit_price is None:
            continue
        opinions = trade.get("agent_contributions") or []
        row: dict[str, float] = {}
        for item in opinions:
            if not isinstance(item, dict) or "feature_contributions" not in item:
                continue
            for feature_name, value in (item.get("feature_contributions") or {}).items():
                row[feature_name] = value
        if row:
            per_trade.append(row)
    return per_trade


def compute_feature_redundancy(
    closed_trades: list[dict], min_sample_size: int = MIN_SAMPLE_SIZE
) -> dict[str, dict]:
    """AYNI trade'de birlikte ateşlenen HER feature çifti için Pearson
    korelasyonu (feature DEĞERİ vs feature DEĞERİ — getiriye karşı değil,
    BİRBİRLERİNE karşı). Anahtar "{a}|{b}" (alfabetik sıralı), değer
    {"correlation", "sample_size"}. min_sample_size altında kalan çiftler
    hiç dönmüyor — fail-closed, feature_ic.py'nin AYNI disiplini."""
    per_trade = _collect_feature_samples(closed_trades)

    pair_samples: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for row in per_trade:
        names = sorted(row.keys())
        for a, b in combinations(names, 2):
            pair_samples[(a, b)].append((row[a], row[b]))

    results: dict[str, dict] = {}
    for (a, b), pairs in pair_samples.items():
        if len(pairs) < min_sample_size:
            continue
        values_a = [p[0] for p in pairs]
        values_b = [p[1] for p in pairs]
        if len(set(values_a)) < 2 or len(set(values_b)) < 2:
            continue
        corr, _p_value = stats.pearsonr(values_a, values_b)
        results[f"{a}|{b}"] = {
            "correlation": round(float(corr), 4),
            "sample_size": len(pairs),
        }
    return results


def compute_conditional_ic(
    closed_trades: list[dict],
    redundancy: dict[str, dict],
    feature_ic: dict[str, dict],
    redundancy_threshold: float = DEFAULT_REDUNDANCY_THRESHOLD,
) -> dict[str, dict]:
    """feature_ic.py::compute_feature_ic'in ürettiği ham IC'lerden,
    |redundancy| >= redundancy_threshold olan HER çift için kapalı-form
    2-değişkenli kısmi korelasyon:

        partial(a, y | b) = (r_ay - r_ab*r_by) / sqrt((1-r_ab^2)(1-r_by^2))

    y = getiri, a/b = birbirine yüksek-redundant iki feature. r_ab bu
    modülün kendi redundancy sonucundan, r_ay/r_by feature_ic'ten geliyor.
    (1-r_ab^2) sıfıra yaklaştıkça (a ve b neredeyse birebir aynıysa)
    payda 0'a yaklaşır — bu durumda kısmi korelasyon tanımsız/anlamsız
    kılınır (fail-closed: None), r_ab=1.0'ye (bu turda gözlenen tam
    çakışma) bölme hatası ASLA fırlatılmaz.

    Gerçek veriyle doğrulama sırasında bulunan ikinci bir dejenere durum:
    r_ab TAM 1.0 değil ama ona ÇOK yakınken (ör. 0.991) payda sıfıra
    yaklaşır ama tam 0 olmaz — bölme ÇALIŞIR ama sonuç örnekleme
    gürültüsüyle patlar (gerçek veride +3.75 gibi bir "korelasyon"
    üretti). Bir kısmi korelasyon KATSAYISI tanım gereği HER ZAMAN
    [-1, 1] aralığındadır — bu aralığın dışına çıkan bir sonuç, gerçek
    bir bulgu DEĞİL, sayısal kararsızlığın kanıtıdır. Bu yüzden |partial|
    > 1 olan sonuçlar da None'a düşürülür (aynı fail-closed disiplini,
    ikinci bir dejenere-payda sınıfına genişletilmiş hali).

    Döner: {feature: {"raw_ic", "conditional_ic_given": {other_feature:
    partial_ic_or_None}}}. Faz A kasıtlı SADECE ikili — a'nın AYNI anda
    birden çok yüksek-redundant komşusuna göre ortak (multi-variable)
    koşullandırılması Faz B'ye bırakıldı."""
    results: dict[str, dict] = {}

    for pair_key, pair_data in redundancy.items():
        if abs(pair_data["correlation"]) < redundancy_threshold:
            continue
        a, b = pair_key.split("|")
        r_ab = pair_data["correlation"]

        for target, other in ((a, b), (b, a)):
            if target not in feature_ic or other not in feature_ic:
                continue
            r_ay = feature_ic[target]["ic"]
            r_by = feature_ic[other]["ic"]

            denom = (1 - r_ab**2) * (1 - r_by**2)
            partial_ic = round((r_ay - r_ab * r_by) / denom**0.5, 4) if denom > 1e-9 else None
            if partial_ic is not None and abs(partial_ic) > 1.0:
                partial_ic = None

            entry = results.setdefault(
                target, {"raw_ic": feature_ic[target]["ic"], "conditional_ic_given": {}}
            )
            entry["conditional_ic_given"][other] = partial_ic

    return results
