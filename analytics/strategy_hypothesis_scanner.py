"""Autonomous Strategy Synthesizer v1 "Regime Gate Discovery" — Faz 346.

Kullanıcı vizyonu: "Autonomous Strategy Synthesizer" — CMA-ES ajan
ayarının (meta_optimizer/agent_tuner.py, Faz 239-241) "ölç → OOS kanıtla
→ insan onayı" zincirinin genellenmiş hali. Kullanıcı onayı (netleştirme
sorusu): v1'in kapsamı bugün BU OTURUMDA elle yapılan sürecin
(SHORT/bearish_low bulgusu, Faz 342) OTOMASYONU — yeni, açık-uçlu
strateji mantığı İCAT EDEN bir sistem DEĞİL. "AI araştırmacı olsun,
trader olmasın" ilkesi (kullanıcı + harici AI incelemesi ortak kararı).

Zincir:
1. `scan_for_gate_candidates()` — strategy_regime_compatibility.py'nin
   zaten kurduğu (strategy × regime) uzayını tarar, bir hücrenin win_rate'i
   AYNI stratejinin GERİ KALANINDAN (hücre HARİÇ, kontaminasyon önlenir)
   istatistiksel olarak anlamlı derecede kötüyse aday olarak işaretler.
   Tek bir çift değil (BTC/ETH gibi), OLASI ONLARCA hücre AYNI ANDA
   test edildiği için (agent_combination_reliability.py'nin Faz 331'de
   zaten çözdüğü AYNI multiple-testing sorunu) Benjamini-Hochberg FDR
   düzeltmesi (analytics/causal_inference.py::apply_fdr_correction)
   uygulanıyor — düzeltmeden GEÇEN adaylar döner.
2. `validate_candidate_out_of_sample()` — walk_forward_validate'in
   (agent_tuner.py) ruhuna sadık: aday, veri zaman sırasına göre ikiye
   bölünüp (embargo boşluklu) SADECE erken yarıda değil GEÇ (hiç
   görülmemiş) yarıda da AYNI yönde kötü çıkıyor mu test ediliyor —
   in-sample ezber değil, gerçekten tekrarlanan bir örüntü mü.

Kasıtlı olarak SADECE ölçüm/rapor/aday üretimi — hiçbir hücreyi
otomatik olarak canlı bir gate'e (MetaStage vb.) BAĞLAMIYOR. Bir aday
burada ne kadar güçlü görünürse görünsün, gerçek bir kod değişikliği
(Faz 342'deki gibi) HER ZAMAN ayrı, açık bir insan kararı gerektirir."""
from analytics.causal_inference import apply_fdr_correction
from analytics.strategy_regime_compatibility import compute_strategy_regime_compatibility

MIN_GROUP_SIZE = 30
# delta_vs_overall bu eşiğin ALTINDAYSA (ör. -0.20 = genel isabetten en
# az 20 puan düşük) aday olarak değerlendirilir — Faz 342'nin SHORT/
# bearish_low bulgusu (-0.193) bu eşiğin hemen altında kalırdı, kasıtlı
# olarak biraz daha sıkı tutuldu (gürültüyü elemek için).
EFFECT_THRESHOLD = -0.20
SIGNIFICANCE_LEVEL = 0.05


def _rest_based_win_rate_and_delta(
    compat: dict, strategy: str, regime: str, min_group_size: int,
) -> tuple[float | None, int | None, float | None]:
    """compute_strategy_regime_compatibility çıktısından, o hücreyi
    HARİÇ tutan (kontaminasyonsuz) "geri kalan" win_rate'i ve deltayı
    türetir — scan_for_gate_candidates ve validate_candidate_out_of_
    sample'ın İKİSİ de bunu kullanıyor, tutarsız iki hesap yöntemi
    olmasın diye. Yetersiz veri varsa (None, None, None)."""
    entry = compat.get(strategy)
    if entry is None:
        return None, None, None
    bucket = entry.get("by_regime", {}).get(regime)
    if bucket is None:
        return None, None, None

    overall_win_rate = entry["overall_win_rate"]
    overall_n = entry["overall_sample_size"]
    if overall_win_rate is None or overall_n == 0:
        return None, None, None
    overall_wins = round(overall_win_rate * overall_n)

    cell_n = bucket["sample_size"]
    cell_wins = round(bucket["win_rate"] * cell_n)
    rest_n = overall_n - cell_n
    rest_wins = overall_wins - cell_wins
    if rest_n < min_group_size:
        return None, None, None
    rest_win_rate = rest_wins / rest_n
    delta_vs_rest = round(bucket["win_rate"] - rest_win_rate, 4)
    return bucket["win_rate"], cell_n, delta_vs_rest


def scan_for_gate_candidates(
    records: list[dict],
    min_group_size: int = MIN_GROUP_SIZE,
    effect_threshold: float = EFFECT_THRESHOLD,
    alpha: float = SIGNIFICANCE_LEVEL,
) -> list[dict]:
    """records: compute_strategy_regime_compatibility'nin beklediği AYNI
    şekil ({'strategy', 'market_regime', 'win'}). Döner: her biri
    {'strategy', 'market_regime', 'sample_size', 'win_rate',
    'rest_win_rate', 'delta_vs_rest', 'p_value'} olan, FDR
    düzeltmesinden GEÇEN aday listesi (boş girdi/aday yoksa [])."""
    from statsmodels.stats.proportion import proportions_ztest

    compat = compute_strategy_regime_compatibility(records, min_group_size=min_group_size)

    raw_candidates = []
    for strategy, entry in compat.items():
        overall_win_rate = entry["overall_win_rate"]
        overall_n = entry["overall_sample_size"]
        if overall_win_rate is None or overall_n == 0:
            continue
        overall_wins = round(overall_win_rate * overall_n)

        for regime, bucket in entry["by_regime"].items():
            cell_n = bucket["sample_size"]
            cell_wins = round(bucket["win_rate"] * cell_n)
            # Kontaminasyon önleme: hücre, "genel"in bir ALT KÜMESİ (ve
            # bazen ÇOĞUNLUĞU — ör. bir strateji/rejim kombinasyonu
            # neredeyse hep AYNI rejimde işlem görüyorsa) — hücreyi
            # kendi kirlenmiş "genel"ine (compute_strategy_regime_
            # compatibility'nin delta_vs_overall'ı) karşı filtrelemek,
            # hücre dominant olduğunda GERÇEK, büyük bir etkiyi
            # gizleyebilirdi (delta_vs_overall küçük çıkar çünkü "genel"
            # zaten çoğunlukla bu hücrenin kendisi). "Geri kalan" (rest),
            # hücre HARİÇ aynı stratejinin tüm diğer kayıtları — gerçek
            # iki-bağımsız-örneklem karşılaştırması, filtre DAHİL her
            # yerde bu kullanılıyor.
            rest_n = overall_n - cell_n
            rest_wins = overall_wins - cell_wins
            if rest_n < min_group_size:
                continue
            rest_win_rate = rest_wins / rest_n
            delta_vs_rest = round(bucket["win_rate"] - rest_win_rate, 4)
            if delta_vs_rest > effect_threshold:
                continue

            try:
                _, p_value = proportions_ztest(
                    count=[cell_wins, rest_wins], nobs=[cell_n, rest_n],
                )
            except Exception:
                continue

            raw_candidates.append({
                "strategy": strategy,
                "market_regime": regime,
                "sample_size": cell_n,
                "win_rate": bucket["win_rate"],
                "rest_win_rate": round(rest_win_rate, 4),
                "delta_vs_rest": delta_vs_rest,
                "p_value": round(float(p_value), 6),
            })

    if not raw_candidates:
        return []

    significant = apply_fdr_correction([c["p_value"] for c in raw_candidates], alpha=alpha)
    return [c for c, sig in zip(raw_candidates, significant) if sig]


def validate_candidate_out_of_sample(
    records_sorted_by_time: list[dict],
    candidate: dict,
    train_fraction: float = 0.5,
    embargo_fraction: float = 0.02,
    min_group_size: int = MIN_GROUP_SIZE,
    effect_threshold: float = EFFECT_THRESHOLD,
) -> dict:
    """records_sorted_by_time: AYNI kayıtlar ama zaman sırasına göre
    (en eski -> en yeni). walk_forward_validate'in (agent_tuner.py) ruhu:
    aday desen SADECE erken yarıda değil, hiç görülmemiş GEÇ yarıda da
    (embargo boşluklu — sınırdaki bir kaydın erken tarafa sızmaması için)
    AYNI yönde kötü çıkıyor mu. İki yarı arasında `replicated_out_of_
    sample` (bool) — desen gerçekten tekrarlanan mı yoksa tek bir
    dönemin tesadüfü mü."""
    n = len(records_sorted_by_time)
    train_end = int(n * train_fraction)
    test_start = train_end + int(n * embargo_fraction)

    train_records = records_sorted_by_time[:train_end]
    test_records = records_sorted_by_time[test_start:]

    train_compat = compute_strategy_regime_compatibility(train_records, min_group_size=min_group_size)
    test_compat = compute_strategy_regime_compatibility(test_records, min_group_size=min_group_size)

    train_win_rate, train_n, _ = _rest_based_win_rate_and_delta(
        train_compat, candidate["strategy"], candidate["market_regime"], min_group_size,
    )
    test_win_rate, test_n, test_delta_vs_rest = _rest_based_win_rate_and_delta(
        test_compat, candidate["strategy"], candidate["market_regime"], min_group_size,
    )

    # Herhangi bir negatif delta değil — AYNI (ekonomik olarak anlamlı)
    # kötülük derecesi, KONTAMİNASYONSUZ (hücre hariç "geri kalan"a
    # karşı) tekrarlanmalı — aksi halde hücre kendi stratejisinin
    # çoğunluğuysa (ör. bu strateji zaten neredeyse hep bu rejimde
    # işlem görüyorsa) küçük görünen bir kirli delta yanlışlıkla
    # "tekrarlanmadı" sayılırdı.
    replicated = test_delta_vs_rest is not None and test_delta_vs_rest <= effect_threshold

    return {
        "train_win_rate": train_win_rate,
        "train_sample_size": train_n,
        "test_win_rate": test_win_rate,
        "test_sample_size": test_n,
        "test_delta_vs_rest": test_delta_vs_rest,
        "replicated_out_of_sample": replicated,
    }
