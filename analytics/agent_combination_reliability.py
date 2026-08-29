"""Agent Combination Reliability — Faz 331 (harici bir AI incelemesi +
kullanıcı isteği, defalarca gündeme gelip ertelenmiş bir madde).

Opportunity Quality (analytics/opportunity_quality.py) council'in KAÇ
ajanın anlaştığını (agreement skoru, 0-1) win_rate ile ilişkilendiriyor
— ama HANGİ ajanların anlaştığı sorusunu hiç sormuyor. Bu modül tam o
soruyu cevaplıyor: belirli bir ajan İKİLİSİ nihai yönle aynı yönde oy
verdiğinde (agreement skorundan BAĞIMSIZ olarak), gerçekleşen win_rate
genel ortalamadan farklı mı?

Neden başta SADECE ikili (pairwise), tekli ya da tam-küme değildi: 9
oy-veren domain için tam altküme uzayı 2^9=512 — o zamanki veri hacmiyle
(~1400 kapanmış işlem) hücre başına örneklem anlamsızca küçülürdü, aşırı
uydurma (overfitting) riski çok yüksek olurdu. Tekli (agent_ablation.py
zaten bunu, ÇOK daha güçlü bir yöntemle — karşı-olgusal leave-one-out
rekonstrüksiyonla — yapıyor) "hangi ajan tek başına pivot" sorusunu
cevaplıyor ama "hangi ajan GRUBU birlikte güçlü" sorusunu cevaplamıyor.

Faz 367-devam — kullanıcı isteği: "örneklem arttıkça kombinasyon boyutu
(A,B → A,B,C → A,B,C,D) organik olarak büyüyemez mi?" Sabit "ikili"
yerine artık BİRDEN FAZLA boyut (varsayılan 2/3/4) AYNI ANDA test
ediliyor — min_group_size eşiği hangi boyutun/hangi grubun yeterli
veriye sahip olduğunu doğal olarak filtreliyor, ayrı bir "mod" yok.
Veri arttıkça üçlüler/dörtlüler kendiliğinden tabloya girer. Tüm
boyutlar AYNI ANDA test edildiği için (causal_inference.py'deki AYNI
multiple-testing endişesi) FDR düzeltmesi TÜM adaylar üzerinde birlikte
uygulanıyor — boyut sayısı arttıkça haklı olarak daha muhafazakâr olur.

Kullanıcı bulgusu (2026-08-28): aynı domaini paylaşan gruplar (ör. bir
3'lü ve onu içeren bir 2'li) çoğu zaman AYNI işlemleri sayıyor — "kaç
bağımsız bulgu" sorusunu yanıtlamak için her grubun, domain paylaşan
diğer gruplarla (boyutundan BAĞIMSIZ) ne kadar örtüştüğü de raporlanıyor.

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir pozisyon/risk/ajan-ağırlık
kararını burada otomatik değiştirmiyor.

Faz 368 — kullanıcı bulgusu (harici bir GPT incelemesi + canlı doğrulama):
24 farklı grup birebir aynı win_rate_delta_vs_baseline (0.2965) veriyordu.
Kod seviyesinde delta formülünde bug YOK (basitçe win_rate - baseline) ve
outcome hiçbir eligibility kararını etkilemiyor (leakage yok) — canlı
veriyle doğrulandı: pattern+sentiment grubunun (n=166, win_rate=%100)
TAMAMI 20-22 Ağustos arası ~42 saatlik TEK bir pencereden, hepsi LONG.
Yani ölçüm YANLIŞ değil — o dar pencerede piyasa gerçekten öyle sert bir
ralli yapmış ki hangi kombinasyon LONG'a katıldıysa otomatik kazanmış.
Mevcut max_shared_trade_overlap_pct SADECE domain-paylaşımlı gruplar
arasındaki örtüşmeyi yakalıyordu — farklı domain kombinasyonlarına sahip
ama AYNI dar zaman penceresinden gelen iki grubu YAKALAMIYORDU. Bu yüzden
her adayın kaç FARKLI takvim gününe yayıldığı da (distinct_days) rapor
ediliyor — düşük distinct_days + yüksek win_rate, "bağımsız kombinasyon
sinerjisi" değil "dar bir rejim/dönem artefaktı" ihtimalini güçlendiren
dürüst bir uyarı (overlap ile AYNI ilke, ayrı bir eksen)."""
from collections import defaultdict
from itertools import combinations

from analytics.agent_ablation import reconstruct_opinions
from analytics.causal_inference import apply_fdr_correction
from analytics.collective_intelligence import compute_accuracy_confidence_interval

MIN_GROUP_SIZE = 20
DEFAULT_COMBINATION_SIZES = (2, 3, 4)
# Faz 373 — kullanıcı isteği (kapsamlı tasarım, 2026-08-29): "effective_
# sample_size + incremental_value + out_of_sample_survival" zenginleştirmesi.
# strategy_hypothesis_scanner.py::validate_candidate_out_of_sample ile AYNI
# temporal split deseni (walk_forward_validate'in ruhu) — erken yarıda
# eğitilen bir örüntü, embargo boşluklu GEÇ yarıda da tekrarlanıyor mu.
OOS_TRAIN_FRACTION = 0.5
OOS_EMBARGO_FRACTION = 0.02
MIN_OOS_TEST_SIZE = 8


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


def _compute_oos_survival(group: list[dict], baseline_win_rate: float) -> bool | None:
    """strategy_hypothesis_scanner.py::validate_candidate_out_of_sample ile
    AYNI walk-forward ruhu: grubun KENDİ kayıtları zaman sırasına göre
    (closed_at) ikiye bölünür (embargo boşluklu), aday örüntü SADECE erken
    yarıda değil hiç görülmemiş GEÇ yarıda da (win_rate > baseline) tekrar
    ediyor mu. Yeterli veri yoksa (test yarısı MIN_OOS_TEST_SIZE'ın altında,
    ya da closed_at eksikse) None — icat edilmiş bir sonuç üretilmez."""
    dated = sorted(
        (r for r in group if r.get("closed_at") is not None),
        key=lambda r: r["closed_at"],
    )
    n = len(dated)
    if n == 0:
        return None
    train_end = int(n * OOS_TRAIN_FRACTION)
    test_start = train_end + int(n * OOS_EMBARGO_FRACTION)
    test_records = dated[test_start:]
    if len(test_records) < MIN_OOS_TEST_SIZE:
        return None
    test_wins = sum(1 for r in test_records if r["win"])
    test_win_rate = test_wins / len(test_records)
    return test_win_rate > baseline_win_rate


def compute_combination_reliability(
    records: list[dict],
    combination_sizes: tuple[int, ...] = DEFAULT_COMBINATION_SIZES,
    min_group_size: int = MIN_GROUP_SIZE,
) -> dict:
    """records: her biri {'agreeing_domains': frozenset[str], 'win': bool}
    olan GERÇEK kapanmış işlemler (agreeing_domains_for_decision'ın her
    gerçek karar için ürettiği). Domain evrenindeki HER kombinasyon (2'li,
    3'lü, 4'lü — combination_sizes) için: grubun TAMAMI agreeing_domains
    içindeyken ("all_agree") gerçekleşen win_rate'i, tüm örneklemin genel
    ("baseline") win_rate'iyle karşılaştırır. min_group_size altındaki
    "all_agree" kovaları fail-closed dışlanır (icat edilmiş bir oran
    asla üretilmez) — veri arttıkça daha büyük gruplar kendiliğinden bu
    eşiği geçip tabloya girer.

    Çoklu-test düzeltmesi: TÜM boyutlardaki adaylar AYNI ANDA test
    edildiği için (causal_inference.py'deki AYNI multiple-testing
    endişesi), her adayın all_agree/baseline win_rate farkının anlamlılığı
    iki-oranlı z-testiyle hesaplanıp Benjamini-Hochberg FDR ile
    düzeltiliyor — ham p<0.05 YETERLİ DEĞİL, sadece FDR'ı da geçenler
    'fdr_significant' ile işaretleniyor (satır silinmiyor, etiketleniyor)."""
    valid = [r for r in records if r.get("agreeing_domains") is not None and r.get("win") is not None]
    if not valid:
        return {"pairs": [], "baseline_win_rate": None, "baseline_sample_size": 0}

    baseline_wins = sum(1 for r in valid if r["win"])
    baseline_win_rate = round(baseline_wins / len(valid), 4)

    all_domains: set[str] = set()
    for r in valid:
        all_domains |= r["agreeing_domains"]

    groups: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for size in combination_sizes:
        for combo in combinations(sorted(all_domains), size):
            combo_set = frozenset(combo)
            for r in valid:
                if combo_set <= r["agreeing_domains"]:
                    groups[combo].append(r)

    # Kullanıcı bulgusu (2026-08-28): "onchain'in 5 çifti de BİREBİR aynı
    # %100.0/+29.4 puan veriyor — bunlar bağımsız bulgu mu yoksa aynı
    # işlemlerin tekrar sayımı mı?" Haklı — bir işlemde 5 ajan aynı anda
    # anlaşırsa, o TEK işlem C(5,2)=10 farklı çiftin (VE her büyüklükten
    # onu kapsayan grubun) örneklemine birden giriyor; FDR bunu düzeltmiyor
    # (çoklu-test için, örtüşen örneklem için değil). Her grubun, en az bir
    # domaini paylaşan diğer TÜM gruplarla (boyutundan BAĞIMSIZ — bir 3'lü,
    # onu içeren bir 2'liyle de karşılaştırılıyor; id() ile GERÇEK işlem
    # kimliği karşılaştırılarak, records yeniden kopyalanmıyor referans
    # paylaşılıyor) ne kadar örtüştüğü hesaplanıp raporlanıyor — yüksek
    # örtüşme, "bağımsız grup sinerjisi" iddiasını zayıflatan dürüst bir
    # uyarı.
    group_id_sets = {key: {id(r) for r in group} for key, group in groups.items() if len(group) >= min_group_size}

    candidates = []
    for domains, group in groups.items():
        if len(group) < min_group_size:
            continue
        wins = sum(1 for r in group if r["win"])
        domains_set = set(domains)
        own_ids = group_id_sets[domains]
        max_overlap_pct = 0.0
        max_overlap_with: tuple[str, ...] | None = None
        for other_key, other_ids in group_id_sets.items():
            if other_key == domains:
                continue
            if domains_set.isdisjoint(other_key):
                continue
            overlap = len(own_ids & other_ids) / len(own_ids)
            if overlap > max_overlap_pct:
                max_overlap_pct = overlap
                max_overlap_with = other_key
        closed_dates = {r["closed_at"].date() for r in group if r.get("closed_at") is not None}
        # Faz 373 — kullanıcı isteği: "effective_sample_size" — max_shared_
        # trade_overlap_pct'in HAM sample_size'ı değiştirmeden sadece
        # yanında bir uyarı olarak durması, "kaç bağımsız bulgu var"
        # sorusunu dolaylı bırakıyordu. Burada AÇIKÇA örtüşme oranı kadar
        # indirgenmiş, "gerçekte ne kadar bağımsız kanıt var" sayısı —
        # asla ham sample_size'ın üstüne çıkmaz, sadece küçültür.
        effective_sample_size = round(len(group) * (1 - max_overlap_pct), 2)
        oos_survival = _compute_oos_survival(group, baseline_win_rate)
        candidates.append({
            "domains": list(domains),
            "combination_size": len(domains),
            "sample_size": len(group),
            "effective_sample_size": effective_sample_size,
            "win_rate": round(wins / len(group), 4),
            "win_rate_ci": compute_accuracy_confidence_interval(wins, len(group)),
            "max_shared_trade_overlap_pct": round(max_overlap_pct, 4),
            "max_shared_trade_overlap_with": list(max_overlap_with) if max_overlap_with else None,
            "distinct_days": len(closed_dates) if closed_dates else None,
            "oos_survival": oos_survival,
            "_wins": wins,
        })

    p_values = [
        _two_proportion_p_value(c["_wins"], c["sample_size"], baseline_wins, len(valid))
        for c in candidates
    ]
    fdr_flags = apply_fdr_correction(p_values)

    # Faz 373 — kullanıcı isteği: "incremental_value" — bir GRUBUN (ör. bir
    # 3'lü) kendi (N-1)-alt-kümelerinden (ör. onu oluşturan 2'liler) EN
    # İYİSİNİ ne kadar geçtiği. agent_ablation.py'nin tekil-ajan pivot
    # sorusunun grup-seviyesi analogu: "bu ek ajan/domain GERÇEKTEN yeni
    # bilgi mi katıyor, yoksa zaten en güçlü alt-kümenin taşıdığı sinyali
    # mi tekrarlıyor?" Karşılaştırılabilir bir alt-küme yoksa (ör. en
    # küçük boyuttaki bir grup, ya da hiçbir (N-1)-alt-kümesi min_group_
    # size'ı geçmediyse) None — icat edilmiş bir fark üretilmez.
    win_rate_by_domains = {tuple(c["domains"]): c["win_rate"] for c in candidates}

    pairs = []
    for c, fdr_ok in zip(candidates, fdr_flags):
        c = dict(c)
        del c["_wins"]
        c["win_rate_delta_vs_baseline"] = round(c["win_rate"] - baseline_win_rate, 4)
        c["fdr_significant"] = fdr_ok

        incremental_value = None
        if c["combination_size"] > 1:
            subset_win_rates = [
                win_rate_by_domains[subset]
                for subset in combinations(c["domains"], c["combination_size"] - 1)
                if subset in win_rate_by_domains
            ]
            if subset_win_rates:
                incremental_value = round(c["win_rate"] - max(subset_win_rates), 4)
        c["incremental_value"] = incremental_value

        # Faz 373 — kullanıcı isteği: "gate_eligible" — üç şartın (istatistiksel
        # anlamlılık + zamansal tekrarlanabilirlik + yeterli bağımsız kanıt)
        # HEPSİNİN birden karşılandığı TEK bir bakışta okunabilir bayrak.
        # Kasıtlı olarak SADECE bir etiket — hiçbir gate/karar hattına
        # otomatik bağlanmıyor, insan onayı hâlâ ayrı ve gerekli.
        c["gate_eligible"] = bool(
            fdr_ok
            and c["oos_survival"] is True
            and c["effective_sample_size"] >= min_group_size
        )
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
