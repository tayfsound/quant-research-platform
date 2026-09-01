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
    compute_oos_survival,
    two_proportion_p_value,
)
from analytics.causal_inference import apply_fdr_correction
from analytics.collective_intelligence import compute_accuracy_confidence_interval

DEFAULT_COMBINATION_SIZES = (2, 3)


def compute_historical_analogs(
    records: list[dict],
    combination_sizes: tuple[int, ...] = DEFAULT_COMBINATION_SIZES,
    min_group_size: int = MIN_GROUP_SIZE,
) -> dict:
    """records: her biri {'agreeing_domains': frozenset[str], 'market_regime':
    str | None, 'direction': 'LONG'|'SHORT', 'win': bool, 'closed_at':
    datetime | None, 'reversing': bool | None} olan GERÇEK kapanmış
    kararlar. Domain evrenindeki HER kombinasyon (2/3'lü) × gerçek
    market_regime × direction × reversing dörtlüsü için: o dörtlünün
    (agreeing_domains ÜST KÜMESİ olan kararlarda) win_rate'ini tüm
    örneklemin baseline'ıyla karşılaştırır. agent_combination_
    reliability.py::compute_combination_reliability ile AYNI istatistiksel
    iskelet — dördüncü eksen (reversing, Faz 404) eklendiği için
    min_group_size ve effective_sample_size korumaları AYNEN uygulanıyor
    (örneklem daha kolay parçalanır, icat edilmiş sonuç riski artmasın
    diye). `reversing` None olan kayıtlar (Faz 401'den — 2026-09-01 —
    ÖNCEKİ kararlar, bu alan hiç kaydedilmemiş) dışlanır — fail-closed,
    icat edilmiş bir reversing değeri asla varsayılmaz."""
    valid = [
        r for r in records
        if r.get("agreeing_domains") is not None
        and r.get("market_regime")
        and r.get("direction") in ("LONG", "SHORT")
        and r.get("win") is not None
        and isinstance(r.get("reversing"), bool)
    ]
    if not valid:
        return {"analogs": [], "baseline_win_rate": None, "baseline_sample_size": 0}

    baseline_wins = sum(1 for r in valid if r["win"])
    baseline_win_rate = round(baseline_wins / len(valid), 4)

    all_domains: set[str] = set()
    for r in valid:
        all_domains |= r["agreeing_domains"]

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for size in combination_sizes:
        for combo in combinations(sorted(all_domains), size):
            combo_set = frozenset(combo)
            for r in valid:
                if combo_set <= r["agreeing_domains"]:
                    groups[(combo, r["market_regime"], r["direction"], r["reversing"])].append(r)

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
        domains, regime, direction, reversing = key
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
        candidates.append({
            "domains": list(domains),
            "market_regime": regime,
            "direction": direction,
            "reversing": reversing,
            "combination_size": len(domains),
            "sample_size": len(group),
            "effective_sample_size": effective_sample_size,
            "win_rate": round(wins / len(group), 4),
            "win_rate_ci": compute_accuracy_confidence_interval(wins, len(group)),
            "max_shared_trade_overlap_pct": round(max_overlap_pct, 4),
            "distinct_days": len(closed_dates) if closed_dates else None,
            "oos_survival": oos_survival,
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
        # agent_combination_reliability.py'nin AYNI üç-şartlı bayrağı:
        # FDR-anlamlı + OOS'ta tekrarlanmış + yeterli bağımsız örneklem.
        # Kasıtlı olarak SADECE bir etiket — hiçbir gate/karar hattına
        # bağlı değil, bu turda insan (kullanıcı) bunu SADECE görüyor.
        c["gate_eligible"] = bool(
            fdr_ok and c["oos_survival"] is True and c["effective_sample_size"] >= min_group_size
        )
        analogs.append(c)

    analogs.sort(key=lambda a: a["win_rate"], reverse=True)
    return {
        "analogs": analogs,
        "baseline_win_rate": baseline_win_rate,
        "baseline_sample_size": len(valid),
    }
