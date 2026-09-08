"""FIL Faz D — Historical Analog Engine (kullanıcı isteği, 2026-08-31):
"bu koşullar (ajan kombinasyonu + rejim) daha önce birlikte görüldüğünde
gerçekte ne olmuş" sorusuna gerçek geçmiş veriyle, tamamen şeffaf/saf-
fonksiyon tabanlı bir cevap — bir ML sınıflandırıcı DEĞİL.

Bağlam: bu oturumda case-based/analog-reasoning yaklaşımına karşı
temkinliliğin gerekçesi olarak yanlış bir "OOS'ta -%32.2 puan tersine
döndü" iddiası kullanılmıştı — gerçek kayıt bunun tersini gösteriyor
(strategy_hypothesis_scanner.py'nin TEK gerçek uçtan-uca adayı OOS'ta
GERÇEKTEN tekrarlandı, hâlâ canlıda kullanılıyor). Bu modül, o başarılı
örneğin istatistiksel korumalarını (FDR + embargo'lu temporal-split OOS +
min örneklem + örtüşme-düzeltmeli effective_sample_size —
analytics/agent_combination_reliability.py) BİREBİR yeniden kullanıyor,
üçüncü bir eksen (market_regime) ekliyor.

Kasıtlı olarak offline/analiz-only — karar hattına BAĞLANMIYOR bu turda
(ayrı bir onay turu gerektirir, plan dosyasında kayıtlı).

Faz 404 (2026-09-01, Market State Katmanı Faz 4 — bkz. ~/.claude/plans/
velvety-whistling-parasol.md) — dördüncü eksen: market_data.features.
market_state_engine::compute_market_state()'in `reversing` bayrağı
(Welch t-test, piyasanın ölçülen yönü az önce döndüğünde True). Soru:
"bu ajan kombinasyonu × rejim × yön üçlüsü, piyasa TAM O ANDA tersine
dönüyorken de mi güvenilir, yoksa sadece sakin dönemlerde mi?" Bu alan
SADECE 2026-09-01'den (Faz 401) SONRAKİ kararlarda kaydedildi — daha
eski hiçbir kararda yok, bu yüzden bugün itibariyle `gate_eligible`
sayısı örneklem yetersizliğinden ~0'a çöküyor OLABİLİR — modülün kendi
min_group_size/effective_sample_size korumaları bunu zaten kendiliğinden
zararsız bir no-op'a indirgiyor, veri zamanla birikince örgü organik
olarak dolacak."""
from collections import defaultdict
from itertools import combinations

from analytics.agent_combination_reliability import (
    MIN_GROUP_SIZE,
    MIN_OOS_TEST_SIZE,
    OOS_EMBARGO_FRACTION,
    OOS_TRAIN_FRACTION,
    compute_oos_survival,
    two_proportion_p_value,
)
from analytics.causal_inference import apply_fdr_correction
from analytics.collective_intelligence import compute_accuracy_confidence_interval

DEFAULT_COMBINATION_SIZES = (2, 3)


DEFAULT_MIN_DISTINCT_DAYS = 5

# Faz 428 — analytics/strategy_hypothesis_scanner.py::EFFECT_THRESHOLD ile
# AYNI büyüklük (-0.20) — "Negative Evidence"nin agent-kombinasyon
# eksenindeki simetriği, kasıtlı olarak oradan import EDİLMİYOR (o modül
# rejim×yön×tür eksenine özel bir tarayıcı, burası ayrı bir istatistiksel
# iskelet — sadece eşik büyüklüğü paylaşılıyor).
HARMFUL_EFFECT_THRESHOLD = -0.20


# Faz 434 (2026-09-07) — kullanıcı isteği: "Temporal Decay/Recency"
# (GPT'nin örneği: bir örüntü Mart'ta %91 iken Ağustos'ta %73'e
# bozulmuş olabilir, "toplam %84" diye görünüp aslında çürüyor).
# Doğal yol haftalık snapshot geçmişinden (Measurement Stability'nin
# compute_stability'si) olurdu — ama gerçek veri kontrol edildi:
# historical_analog_snapshots'ta şu an sadece 2 nokta var (Faz 431'in
# bulduğu AYNI veri kıtlığı, hafta hafta bir trend hesaplamaya yetmiyor).
# Bunun yerine, compute_oos_survival()'ın ZATEN kullandığı kronolojik
# erken/geç yarı bölünmesi (embargo boşluklu) genişletiliyor — SADECE
# bool bir "hayatta kaldı mı" değil, gerçek erken/geç win_rate
# SAYILARINI açığa çıkarıyor. Snapshot geçmişi beklemeden BUGÜN, mevcut
# 2000-karar penceresinin İÇİNDEN hesaplanabiliyor.
def compute_recency_decay(group: list[dict]) -> dict | None:
    """group: AYNI analog hücresine düşen kararlar. compute_oos_survival
    ile AYNI train/test bölünmesi (OOS_TRAIN_FRACTION/OOS_EMBARGO_
    FRACTION) — ama sonucu bool'a indirgemek yerine iki yarının GERÇEK
    win_rate'ini döndürüyor. Her iki yarı da MIN_OOS_TEST_SIZE'ı
    geçmezse None (icat edilmiş bir eğim asla üretilmez)."""
    dated = sorted(
        (r for r in group if r.get("closed_at") is not None),
        key=lambda r: r["closed_at"],
    )
    n = len(dated)
    if n == 0:
        return None
    train_end = int(n * OOS_TRAIN_FRACTION)
    test_start = train_end + int(n * OOS_EMBARGO_FRACTION)
    early_records = dated[:train_end]
    late_records = dated[test_start:]
    if len(early_records) < MIN_OOS_TEST_SIZE or len(late_records) < MIN_OOS_TEST_SIZE:
        return None

    early_win_rate = round(sum(1 for r in early_records if r["win"]) / len(early_records), 4)
    late_win_rate = round(sum(1 for r in late_records if r["win"]) / len(late_records), 4)
    return {
        "early_win_rate": early_win_rate,
        "late_win_rate": late_win_rate,
        "decay": round(late_win_rate - early_win_rate, 4),
        "early_n": len(early_records),
        "late_n": len(late_records),
        "early_period_end": early_records[-1]["closed_at"].isoformat(),
        "late_period_start": late_records[0]["closed_at"].isoformat(),
    }


def compute_historical_analogs(
    records: list[dict],
    combination_sizes: tuple[int, ...] = DEFAULT_COMBINATION_SIZES,
    min_group_size: int = MIN_GROUP_SIZE,
    min_distinct_days: int = DEFAULT_MIN_DISTINCT_DAYS,
) -> dict:
    """records: her biri {'agreeing_domains': frozenset[str], 'market_regime':
    str | None, 'direction': 'LONG'|'SHORT', 'win': bool, 'closed_at':
    datetime | None, 'reversing': bool | None, 'volatility_regime':
    str | None, 'structure_phase': str | None, 'trade_type': 'scalp'|
    'swing'|None} olan GERÇEK kapanmış kararlar. Domain evrenindeki HER
    kombinasyon (2/3'lü) × market_regime × direction × reversing ×
    volatility_regime × structure_phase × trade_type YEDİLİSİ için: o
    yedilinin (agreeing_domains ÜST KÜMESİ olan kararlarda) win_rate'ini
    tüm örneklemin baseline'ıyla karşılaştırır — kullanıcının 2026-09-06
    kararının ("state'i REGIME+DIRECTION+AGENT STATE+VOLATILITY+MARKET
    STRUCTURE+FEATURE STATE+TIME/HORIZON'a genişlet") 7 boyutunun TAMAMI:
    AGENT STATE=domains, REGIME=market_regime, DIRECTION=direction,
    FEATURE STATE=reversing (Faz 404, market_state_engine'den TÜRETİLMİŞ
    gerçek bir özellik durumu), VOLATILITY=volatility_regime, MARKET
    STRUCTURE=structure_phase (Wyckoff), TIME/HORIZON=trade_type (scalp/
    swing). agent_combination_reliability.py::compute_combination_
    reliability ile AYNI istatistiksel iskelet — kullanıcının KENDİ
    öngördüğü/kabul ettiği sonuç: 4→7 eksene çıkmak örneklemi ÇOK daha
    kolay parçalar, min_group_size/FDR/effective_sample_size korumaları
    AYNEN (gevşetilmeden) uygulanıyor, gate_eligible sayısının uzun süre
    ~0 kalması beklenen/zararsız bir no-op (Faz 404'ün 'reversing'
    eksenindeki AYNI öngörü). Yeni 3 alandan HERHANGİ biri eksik/None
    olan kayıt dışlanır — fail-closed, icat edilmiş bir durum asla
    varsayılmaz (reversing'in Faz 401 öncesi kararları dışlaması İLE
    AYNI ilke)."""
    valid = [
        r for r in records
        if r.get("agreeing_domains") is not None
        and r.get("market_regime")
        and r.get("direction") in ("LONG", "SHORT")
        and r.get("win") is not None
        and isinstance(r.get("reversing"), bool)
        and r.get("volatility_regime")
        and r.get("structure_phase")
        and r.get("trade_type") in ("scalp", "swing")
    ]
    if not valid:
        return {"analogs": [], "baseline_win_rate": None, "baseline_sample_size": 0}

    baseline_wins = sum(1 for r in valid if r["win"])
    baseline_win_rate = round(baseline_wins / len(valid), 4)

    all_domains: set[str] = set()
    for r in valid:
        all_domains |= r["agreeing_domains"]

    groups: dict[tuple, list[dict]] = defaultdict(list)
    # Faz 427 — kullanıcı isteği: "incremental value" ölçümü. agent_
    # combination_reliability.py'nin KENDİ "bir ajan daha eklemenin
    # değeri" sorusundan FARKLI bir soru: "rejim/yön/reversing ile
    # KOŞULLANDIRMAK, sadece ajan kombinasyonunu bilmekten daha mı iyi?"
    # domain_groups, AYNI iç döngüde (ikinci bir geçiş gerekmeden) SADECE
    # domains anahtarıyla (rejim/yön/reversing yok sayılarak) gruplanıyor.
    domain_groups: dict[tuple, list[dict]] = defaultdict(list)
    for size in combination_sizes:
        for combo in combinations(sorted(all_domains), size):
            combo_set = frozenset(combo)
            for r in valid:
                if combo_set <= r["agreeing_domains"]:
                    key = (
                        combo, r["market_regime"], r["direction"], r["reversing"],
                        r["volatility_regime"], r["structure_phase"], r["trade_type"],
                    )
                    groups[key].append(r)
                    domain_groups[combo].append(r)

    # min_group_size altındaki bir domain-only grup icat edilmiş bir
    # karşılaştırma taban değeri üretir — o kombinasyonlar için
    # conditioning_incremental_value aşağıda None kalır (fail-closed).
    domain_only_win_rates = {
        combo: sum(1 for r in group if r["win"]) / len(group)
        for combo, group in domain_groups.items()
        if len(group) >= min_group_size
    }

    # Faz 451 (2026-09-08) — GPT'nin "context-adjusted incremental lift"
    # önerisinin kademeli/cascading kısmı (conditioning_incremental_value,
    # Faz 427, TEK bir karşılaştırma yapıyordu: domain-only vs TAM hücre —
    # rejim/yön/reversing/volatility/structure/trade_type'ın HEPSİNİ TEK
    # ADIMDA katıyordu). Bu, AYNI soruyu AŞAMA AŞAMA soruyor: global
    # taban → rejim tabanı → rejim+yön tabanı → (mevcut conditioning_
    # incremental_value'nun kapsadığı) tam hücre — her adımın KENDİ
    # marjinal katkısını ayırıyor ("bu hücrenin edge'i asıl rejimden mi
    # geliyor, yoksa ajan kombinasyonunun kendisi mi gerçekten katkı
    # sağlıyor?"). Ajan-kombinasyonunun KENDİ aşamalı büyüme sırası
    # (pattern → pattern+technical gibi tek tek ajan ekleme) BİLEREK
    # kapsam dışı bırakıldı — bu, size=1 tekil-ajan hücreleri + hangi
    # ajanın "önce" eklendiğine dair bir sıralama kararı gerektiren, çok
    # daha büyük ayrı bir iş; conditioning_incremental_value (Faz 427)
    # o son adımın YERİNE (domain-only'den tam hücreye TEK sıçrama)
    # geçiyor, tam bir ajan-bazlı kademe değil.
    regime_groups: dict[str, list[dict]] = defaultdict(list)
    regime_direction_groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in valid:
        regime_groups[r["market_regime"]].append(r)
        regime_direction_groups[(r["market_regime"], r["direction"])].append(r)

    regime_win_rates = {
        regime: sum(1 for r in group if r["win"]) / len(group)
        for regime, group in regime_groups.items()
        if len(group) >= min_group_size
    }
    regime_direction_win_rates = {
        key: sum(1 for r in group if r["win"]) / len(group)
        for key, group in regime_direction_groups.items()
        if len(group) >= min_group_size
    }

    # agent_combination_reliability.py'deki AYNI örtüşme mantığı: bir
    # işlem birden fazla (domain, rejim, yön) hücresine birden girebilir
    # (ör. bir 3'lü, onu kapsayan bir 2'liyle) — "bağımsız kanıt"
    # iddiasını zayıflatan dürüst bir düzeltme.
    group_id_sets = {
        key: {id(r) for r in group} for key, group in groups.items() if len(group) >= min_group_size
    }

    candidates = []
    for key, group in groups.items():
        if len(group) < min_group_size:
            continue
        domains, regime, direction, reversing, volatility_regime, structure_phase, trade_type = key
        wins = sum(1 for r in group if r["win"])
        domains_set = set(domains)
        own_ids = group_id_sets[key]
        max_overlap_pct = 0.0
        for other_key, other_ids in group_id_sets.items():
            if other_key == key:
                continue
            if domains_set.isdisjoint(other_key[0]):
                continue
            overlap = len(own_ids & other_ids) / len(own_ids)
            if overlap > max_overlap_pct:
                max_overlap_pct = overlap
        closed_dates = {r["closed_at"].date() for r in group if r.get("closed_at") is not None}
        effective_sample_size = round(len(group) * (1 - max_overlap_pct), 2)
        oos_survival = compute_oos_survival(group, baseline_win_rate)
        # Faz 428 — "Negative Evidence": strategy_hypothesis_scanner.py'nin
        # pozitif/negatif simetrisiyle AYNI ilke, ama agent-kombinasyon
        # ekseninde. compute_oos_survival'ın YÖN parametresi (bkz. o
        # fonksiyonun Faz 428 notu) — pozitif tarafın "OOS'ta baseline'ın
        # ÜSTÜNDE kaldı mı" sorusunun tam simetriği.
        oos_survival_negative = compute_oos_survival(group, baseline_win_rate, direction="negative")
        # Faz 434 — "Temporal Decay/Recency": aynı train/test bölünmesinin
        # GERÇEK erken/geç win_rate sayıları (bkz. modül başındaki not).
        recency_decay = compute_recency_decay(group)
        win_rate = round(wins / len(group), 4)

        # Faz 427 — "rejim/yön/reversing ile koşullandırmak, sadece bu
        # ajan kombinasyonunu bilmekten daha mı iyi?" domain_only_win_
        # rates'te karşılaştırılabilir bir taban yoksa None (icat
        # edilmiş bir fark asla üretilmez) — agent_combination_
        # reliability.py'nin incremental_value'suyla AYNI fail-closed
        # ilke.
        domain_baseline = domain_only_win_rates.get(domains)
        conditioning_incremental_value = (
            round(win_rate - domain_baseline, 4) if domain_baseline is not None else None
        )

        # Faz 451 — kademeli context cascade: global → rejim → rejim+yön
        # → (mevcut conditioning_incremental_value'nun kapsadığı) tam
        # hücre. Her adım fail-closed None (min_group_size altındaki bir
        # ara taban icat edilmiş bir lift üretmez).
        regime_baseline = regime_win_rates.get(regime)
        regime_direction_baseline = regime_direction_win_rates.get((regime, direction))
        lift_from_regime = (
            round(regime_baseline - baseline_win_rate, 4) if regime_baseline is not None else None
        )
        lift_from_direction = (
            round(regime_direction_baseline - regime_baseline, 4)
            if regime_baseline is not None and regime_direction_baseline is not None
            else None
        )
        lift_from_agent_combination = (
            round(win_rate - regime_direction_baseline, 4)
            if regime_direction_baseline is not None
            else None
        )
        context_cascade = {
            "global_baseline": baseline_win_rate,
            "regime_baseline": round(regime_baseline, 4) if regime_baseline is not None else None,
            "regime_direction_baseline": (
                round(regime_direction_baseline, 4) if regime_direction_baseline is not None else None
            ),
            "lift_from_regime": lift_from_regime,
            "lift_from_direction": lift_from_direction,
            "lift_from_agent_combination": lift_from_agent_combination,
        }
        # Faz 427 — "Pattern Coverage": bu hücrenin TÜM örneklemin ne
        # kadarını temsil ettiği. gate_eligible'a KATILMIYOR (zorla bir
        # eşik değil) — sadece "yüksek win_rate ama kararların %0,3'ünü
        # kapsıyor" durumunu şeffaf bırakmak için.
        coverage_pct = round(len(group) / len(valid), 6) if valid else None
        # Faz 449 (2026-09-08) — "Pattern Coverage"nin ertelenmiş küçük
        # parçası: coverage_pct ve conditioning_incremental_value Faz
        # 427'den beri AYRI AYRI mevcuttu ("WR yüksek ama kararların
        # %0,3'ünü kapsıyorsa sınırlı fayda" sorusuna cevap vermek için
        # ikisi BİRLİKTE okunmalıydı, kullanıcı henüz tek bir bileşik
        # skor istemişti). İşaretini KORUYOR (negatif bir incremental
        # value + yüksek coverage = gerçekten zararlı VE yaygın bir
        # örüntü, aynı ilke coverage_pct=0 civarındayken her iki yönde
        # de sıfıra çekiliyor) — icat edilmiş bir ağırlıklandırma değil,
        # basit çarpım (coverage_pct∈[0,1] olduğu için işaret asla
        # değişmez, sadece büyüklük coverage ile ölçekleniyor).
        coverage_weighted_incremental_value = (
            round(coverage_pct * conditioning_incremental_value, 6)
            if coverage_pct is not None and conditioning_incremental_value is not None
            else None
        )

        candidates.append({
            "domains": list(domains),
            "market_regime": regime,
            "direction": direction,
            "reversing": reversing,
            "volatility_regime": volatility_regime,
            "structure_phase": structure_phase,
            "trade_type": trade_type,
            "combination_size": len(domains),
            "sample_size": len(group),
            "effective_sample_size": effective_sample_size,
            "win_rate": win_rate,
            "win_rate_ci": compute_accuracy_confidence_interval(wins, len(group)),
            "max_shared_trade_overlap_pct": round(max_overlap_pct, 4),
            "distinct_days": len(closed_dates) if closed_dates else None,
            "oos_survival": oos_survival,
            "oos_survival_negative": oos_survival_negative,
            "recency_decay": recency_decay,
            "conditioning_incremental_value": conditioning_incremental_value,
            "coverage_pct": coverage_pct,
            "coverage_weighted_incremental_value": coverage_weighted_incremental_value,
            "context_cascade": context_cascade,
            "_wins": wins,
        })

    p_values = [
        two_proportion_p_value(c["_wins"], c["sample_size"], baseline_wins, len(valid))
        for c in candidates
    ]
    fdr_flags = apply_fdr_correction(p_values)

    analogs = []
    for c, fdr_ok in zip(candidates, fdr_flags):
        c = dict(c)
        del c["_wins"]
        c["win_rate_delta_vs_baseline"] = round(c["win_rate"] - baseline_win_rate, 4)
        c["fdr_significant"] = fdr_ok
        # Faz 422 (2026-09-06) — GPT'nin dış incelemesi + kullanıcı onayı:
        # gate_eligible olan analogların TAMAMI distinct_days=2 çıkıyordu
        # (ör. order_flow+technical/bullish_normal/LONG: win_rate=0,94,
        # eff_n=27, SADECE 2 farklı gün) — "2 ayrı zaman kesitinde
        # doğrulandı" gerçek bir zamansal dayanıklılık kanıtı için ÇOK
        # ZAYIF, agent_combination_reliability_gate.py'nin ZATEN
        # kullandığı AYNI min_distinct_days=5 eşiği burada YOKTU. HISTORICAL_
        # ANALOG_OVERRIDE_ENABLED=true iken bu, belief.strength'i sadece
        # 2 günlük kanıtla 0,94'e sıçratabiliyordu, hiçbir küçültme
        # (shrinkage) olmadan — kanıtlanmamış zamansal genelleme riski
        # gerçekti, teorik değil.
        c["gate_eligible"] = bool(
            fdr_ok
            and c["oos_survival"] is True
            and c["effective_sample_size"] >= min_group_size
            and (c["distinct_days"] or 0) >= min_distinct_days
        )
        # Faz 428 — kullanıcı isteği: "Negative Evidence" — gate_eligible
        # ile TAM SİMETRİK ama negatif yönde. Kasıtlı olarak SADECE bir
        # etiket (gate_eligible gibi) — hiçbir gate/karar hattına
        # otomatik bağlanmıyor, insan onayı hâlâ ayrı ve gerekli.
        c["harmful_eligible"] = bool(
            fdr_ok
            and c["oos_survival_negative"] is True
            and c["effective_sample_size"] >= min_group_size
            and (c["distinct_days"] or 0) >= min_distinct_days
            and c["win_rate_delta_vs_baseline"] <= HARMFUL_EFFECT_THRESHOLD
        )
        analogs.append(c)

    analogs.sort(key=lambda a: a["win_rate"], reverse=True)
    return {
        "analogs": analogs,
        "baseline_win_rate": baseline_win_rate,
        "baseline_sample_size": len(valid),
    }


# Faz 433 (2026-09-07) — kullanıcı isteği: "1'den devam edelim" (GPT'nin
# listesindeki "confidence override'ı ham win_rate yerine shrinkage/
# posterior düzeltilmiş bir değerle + maksimum uplift cap'iyle yap"
# maddesi). engines/cognitive_pipeline.py::HistoricalAnalogOverrideStage
# şu an `belief.strength = best["win_rate"]` ile ham değeri DOĞRUDAN
# yazıyor — gate_eligible zaten min_group_size/FDR/OOS/min_distinct_days
# şartlarını sağlıyor ama bu, örneklem gürültüsünün belief.strength'e
# HİÇ küçültülmeden (shrinkage'sız) sızmayacağını garanti etmiyor (küçük
# bir örneklemde şanslı bir seri hâlâ gate_eligible olabilir).
#
# min_group_size (=20) civarındaki bir effective_sample_size, gerçek
# istatistiksel EŞİĞİ geçmiş olsa da hâlâ NİSPETEN az kanıt demek —
# bu yüzden uplift miktarının kendisi (raw_win_rate - strength_before,
# override'ın "kaç puan artıracağı"), effective_sample_size shrinkage_k'yı
# ne kadar AŞTIĞINA göre ölçeklendiriliyor: eff_n=shrinkage_k iken
# uplift'in SADECE yarısı güvenilir sayılır, eff_n büyüdükçe tam uplift'e
# yaklaşılır. `strength_before`'IN ALTINA asla inmez (stage'in kendi
# "SADECE YÜKSELTİR" ilkesiyle AYNI) VE `max_uplift` ile üst sınırlanır
# (market_state_tilt.py::MAX_TILT=0.3 ile AYNI büyüklük — hiçbir tek
# mekanizma belief.strength'i tek seferde aşırı sıçratamaz).
DEFAULT_SHRINKAGE_K = 20.0
MAX_UPLIFT = 0.3


# Faz 445 (2026-09-07) — "Direction Analog": GPT'nin 7 numaralı önceliği
# ("Historical Analog → koşullu direction probability"). compute_
# historical_analogs()'u SIFIRDAN yeniden yazmıyor — o fonksiyon zaten
# "bu koşullar altında win_rate ne" sorusuna FDR+OOS+distinct_days+
# effective_sample_size ile cevap veriyor; burada tek fark 'win'in ne
# anlama geldiği: trade kârlılığı (pnl>0) yerine Faz 441'in `label_
# forward_direction()`'ından gelen sabit-ufuklu UP/DOWN/NEUTRAL etiketi.
# Üç ayrı ikili soru olarak sırayla compute_historical_analogs()'a
# devrediliyor ("bu bağlamda P(UP)?", "P(DOWN)?", "P(NEUTRAL)?") — AYNI
# istatistiksel iskelet üç kez, hiçbir yeni hesap makinesi icat edilmeden.
DIRECTION_LABELS = ("UP", "DOWN", "NEUTRAL")


def compute_direction_analogs(
    records: list[dict],
    combination_sizes: tuple[int, ...] = DEFAULT_COMBINATION_SIZES,
    min_group_size: int = MIN_GROUP_SIZE,
    min_distinct_days: int = DEFAULT_MIN_DISTINCT_DAYS,
) -> dict:
    """records: compute_historical_analogs()'un beklediği AYNI alanlar
    ('agreeing_domains', 'market_regime', 'direction' — kararın kendi
    LONG/SHORT'u, 'reversing', 'volatility_regime', 'structure_phase',
    'trade_type', 'closed_at' — Faz 450'nin 7 boyutu DAHİL) + YENİ 'forward_label':
    'UP'|'DOWN'|'NEUTRAL'|None (Faz 441'in label_forward_direction()'ından
    — bu fonksiyon etiketi HESAPLAMIYOR, hazır bekliyor, tek sorumluluk
    ilkesi). forward_label'ı None/DIRECTION_LABELS dışı olan kayıtlar
    dışlanır (fail-closed). Dönen sözlük {'UP': {...}, 'DOWN': {...},
    'NEUTRAL': {...}} — her biri compute_historical_analogs()'un TAM
    kendi çıktısı (analogs/baseline_win_rate/baseline_sample_size), ama
    burada 'win_rate' alanı GERÇEKTE o etiketin koşullu olasılığı: bir
    hücrenin UP sonucundaki win_rate'i = P(UP | o hücrenin bağlamı)."""
    labeled = [r for r in records if r.get("forward_label") in DIRECTION_LABELS]
    return {
        label: compute_historical_analogs(
            [{**r, "win": r["forward_label"] == label} for r in labeled],
            combination_sizes=combination_sizes,
            min_group_size=min_group_size,
            min_distinct_days=min_distinct_days,
        )
        for label in DIRECTION_LABELS
    }


def apply_confidence_shrinkage(
    raw_win_rate: float,
    effective_sample_size: float,
    strength_before: float,
    shrinkage_k: float = DEFAULT_SHRINKAGE_K,
    max_uplift: float = MAX_UPLIFT,
) -> float:
    """gate_eligible bir analogun ham win_rate'ini, effective_sample_size'a
    göre küçültülmüş (shrunk) bir uplift'e çevirip strength_before'a
    ekler. raw_win_rate <= strength_before ise (yükseltmeyen bir eşleşme)
    hiç değişiklik yapılmaz — 0 <= weight <= 1 olduğu için sonuç HER ZAMAN
    [strength_before, strength_before + max_uplift] aralığında kalır."""
    weight = effective_sample_size / (effective_sample_size + shrinkage_k)
    uplift = weight * (raw_win_rate - strength_before)
    uplift = min(max(uplift, 0.0), max_uplift)
    return strength_before + uplift
