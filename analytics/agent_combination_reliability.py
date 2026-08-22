"""Agent Combination Reliability — Faz 331 (harici bir AI incelemesi +
kullanıcı isteği, defalarca gündeme gelip ertelenmiş bir madde).

Opportunity Quality (analytics/opportunity_quality.py) council'in KAÇ
ajanın anlaştığını (agreement skoru, 0-1) win_rate ile ilişkilendiriyor
— ama HANGİ ajanların anlaştığı sorusunu hiç sormuyor. Bu modül tam o
soruyu cevaplıyor: belirli bir ajan İKİLİSİ nihai yönle aynı yönde oy
verdiğinde (agreement skorundan BAĞIMSIZ olarak), gerçekleşen win_rate
genel ortalamadan farklı mı?

Neden ikili (pairwise), tekli ya da tam-küme değil: 9 oy-veren domain
için tam altküme uzayı 2^9=512 — gerçek veri hacmiyle (şu an ~1400
kapanmış işlem) hücre başına örneklem anlamsızca küçülür, aşırı
uydurma (overfitting) riski çok yüksek olurdu. Tekli (agent_ablation.py
zaten bunu, ÇOK daha güçlü bir yöntemle — karşı-olgusal leave-one-out
rekonstrüksiyonla — yapıyor) "hangi ajan tek başına pivot" sorusunu
cevaplıyor ama "hangi ajan İKİLİSİ birlikte güçlü" sorusunu cevaplamıyor.
İkili (C(9,2)=36 çift) bu ikisinin arasında, istatistiksel olarak hâlâ
savunulabilir bir orta nokta — causal_inference.py'nin BTC/ETH×47 varlık
çift-bazlı test deseniyle AYNI ilke.

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir pozisyon/risk/ajan-ağırlık
kararını burada otomatik değiştirmiyor."""
from collections import defaultdict
from itertools import combinations

from analytics.agent_ablation import reconstruct_opinions
from analytics.causal_inference import apply_fdr_correction
from analytics.collective_intelligence import compute_accuracy_confidence_interval

MIN_GROUP_SIZE = 20


def agreeing_domains_for_decision(agent_contributions: list[dict], final_direction: str) -> frozenset[str] | None:
    """Saklanmış agent_contributions'tan (bazıları AgentOpinion değil —
    market_snapshot/risk_evaluation gibi zarf dict'ler, agent_ablation.py
    ile AYNI rekonstrüksiyon) final_direction ile AYNI yönde oy veren
    domain'lerin kümesini döner. final_direction LONG/SHORT değilse (WAIT
    ya da boş) None — "hangi ajanlar WAIT ile aynı yönde" anlamsız bir
    soru, zorla bir küme üretilmez."""
    if final_direction not in ("LONG", "SHORT"):
        return None
    opinions = reconstruct_opinions(agent_contributions)
    if not opinions:
        return None
    return frozenset(o.domain.value for o in opinions if o.direction == final_direction)


def compute_pairwise_combination_reliability(
    records: list[dict],
    min_group_size: int = MIN_GROUP_SIZE,
) -> dict:
    """records: her biri {'agreeing_domains': frozenset[str], 'win': bool}
    olan GERÇEK kapanmış işlemler (agreeing_domains_for_decision'ın her
    gerçek karar için ürettiği). Domain evrenindeki HER ikili (A, B) için:
    her ikisi de agreeing_domains içindeyken ("both_agree") gerçekleşen
    win_rate'i, tüm örneklemin genel ("baseline") win_rate'iyle
    karşılaştırır. min_group_size altındaki "both_agree" kovaları
    fail-closed dışlanır (icat edilmiş bir oran asla üretilmez).

    Çoklu-test düzeltmesi: 36 çift AYNI ANDA test edildiği için (causal_
    inference.py'deki AYNI multiple-testing endişesi), her çiftin
    both_agree/baseline win_rate farkının anlamlılığı iki-oranlı z-testiyle
    hesaplanıp Benjamini-Hochberg FDR ile düzeltiliyor — ham p<0.05 YETERLİ
    DEĞİL, sadece FDR'ı da geçen çiftler 'fdr_significant' ile
    işaretleniyor (satırın kendisi silinmiyor, sadece etiketleniyor)."""
    valid = [r for r in records if r.get("agreeing_domains") is not None and r.get("win") is not None]
    if not valid:
        return {"pairs": [], "baseline_win_rate": None, "baseline_sample_size": 0}

    baseline_wins = sum(1 for r in valid if r["win"])
    baseline_win_rate = round(baseline_wins / len(valid), 4)

    all_domains: set[str] = set()
    for r in valid:
        all_domains |= r["agreeing_domains"]

    pair_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for domain_a, domain_b in combinations(sorted(all_domains), 2):
        for r in valid:
            if domain_a in r["agreeing_domains"] and domain_b in r["agreeing_domains"]:
                pair_groups[(domain_a, domain_b)].append(r)

    candidates = []
    for (domain_a, domain_b), group in pair_groups.items():
        if len(group) < min_group_size:
            continue
        wins = sum(1 for r in group if r["win"])
        candidates.append({
            "domain_a": domain_a,
            "domain_b": domain_b,
            "sample_size": len(group),
            "win_rate": round(wins / len(group), 4),
            "win_rate_ci": compute_accuracy_confidence_interval(wins, len(group)),
            "_wins": wins,
        })

    p_values = [
        _two_proportion_p_value(c["_wins"], c["sample_size"], baseline_wins, len(valid))
        for c in candidates
    ]
    fdr_flags = apply_fdr_correction(p_values)

    pairs = []
    for c, fdr_ok in zip(candidates, fdr_flags):
        c = dict(c)
        del c["_wins"]
        c["win_rate_delta_vs_baseline"] = round(c["win_rate"] - baseline_win_rate, 4)
        c["fdr_significant"] = fdr_ok
        pairs.append(c)

    pairs.sort(key=lambda p: p["win_rate"], reverse=True)
    return {
        "pairs": pairs,
        "baseline_win_rate": baseline_win_rate,
        "baseline_sample_size": len(valid),
    }


def _two_proportion_p_value(wins_a: int, n_a: int, wins_b: int, n_b: int) -> float:
    """İki bağımsız oranın (both_agree kovası vs TÜM örneklem — örtüşmeleri
    testi muhafazakarlaştırır, ideal iki-bağımsız-örneklem değildir ama
    ucuz/kararlı bir tarama içindir) eşit olduğu sıfır hipotezi için
    standart iki-oranlı z-testi. n=0 ya da sıfır varyans durumunda
    fail-closed p=1.0 (hiçbir zaman anlamlı sayılmaz)."""
    if n_a == 0 or n_b == 0:
        return 1.0
    import math

    p_a = wins_a / n_a
    p_b = wins_b / n_b
    p_pool = (wins_a + wins_b) / (n_a + n_b)
    if p_pool in (0.0, 1.0):
        return 1.0
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b))
    if se == 0:
        return 1.0
    z = (p_a - p_b) / se
    # İki-yönlü p-değeri, standart normal kümülatif dağılımdan.
    p_value = 2 * (1 - _standard_normal_cdf(abs(z)))
    return round(min(max(p_value, 0.0), 1.0), 6)


def _standard_normal_cdf(x: float) -> float:
    import math

    return 0.5 * (1 + math.erf(x / math.sqrt(2)))
