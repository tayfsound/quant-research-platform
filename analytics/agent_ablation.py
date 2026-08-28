"""Agent Ablation — Faz 296. Kullanıcı isteği (2026-08-19): mevcut auto-
bench (agents/source_reliability_agent.py) SADECE davranışsal/geriye
dönük doğruluk ölçüyor — "bu ajan geçmişte ne kadar isabetliydi" sorusuna
cevap veriyor, ama "bu ajanın oyu OLMASAYDI, gerçekleşen kararlar farklı
olur muydu, o karar hiç açılır mıydı" sorusunu hiç sormuyor. Bu modül
GERÇEK bir leave-one-out (nedensel) rekonstrüksiyon yapıyor: kapanmış
her gerçek kararın SAKLANMIŞ agent_contributions'ından (services/
belief_engine.py::synthesize zaten pure/deterministik bir fonksiyon)
hedef ajanın oyu SIFIRLANIP council'in belief-fusion aşaması yeniden
çalıştırılıyor.

Dürüstçe SINIRLI kapsam: sadece belief-fusion aşamasını (synthesize)
yeniden çalıştırıyor, DecisionFusion'ın sonraki confidence-kalibrasyon/
EV-kapısı aşamalarını DEĞİL (bunlar için o anki kalibrasyon eğrisi/EV
varsayımları gerekir, tarihsel olarak güvenilir şekilde yeniden
üretilemez). Bu yüzden "caused_trade" (bu ajan OLMASAYDI işlem hiç
AÇILMAZDI) SADECE en temiz, en dürüst durumda sayılıyor: karşı-olgusal
synthesize sonucunun kendisi WAIT'e düşüyorsa (hiçbir yönlü ağırlık
kalmıyorsa) — bu durumda downstream hangi eşik kullanılırsa kullanılsın
işlem KESİNLİKLE açılamazdı, çünkü yönlü bir belief bile yok. Yön
DEĞİŞEN (ama hâlâ yönlü bir belief üreten) durumlar ayrı ve daha zayıf
bir kategoride ("flipped_direction") sayılıyor — bunlara pnl atfetmek
icat edilmiş bir sayı üretmek olurdu, o yüzden yapılmıyor.

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir ajanın canlı oy hakkını
burada otomatik değiştirmiyor."""
from collections import defaultdict

from analytics.collective_intelligence import compute_accuracy_confidence_interval
from contracts.agent import AgentOpinion


def reconstruct_opinions(agent_contributions: list[dict]) -> list[AgentOpinion]:
    """Saklanmış agent_contributions listesinden (bazıları AgentOpinion
    değil — market_snapshot/risk_evaluation/decision_fusion gibi zarf
    dict'ler) SADECE gerçek ajan oylarını (domain alanı olanları) geri
    kurar. Bozuk/eksik bir kayıt sessizce atlanır (fail-closed) —
    tek bir kötü satır tüm rekonstrüksiyonu çökertmez."""
    opinions = []
    for item in agent_contributions or []:
        if not isinstance(item, dict) or "domain" not in item:
            continue
        try:
            opinion = AgentOpinion(**item)
        except Exception:
            continue
        # Gerçek veriyle bulundu: bazı eski kayıtlarda direction hiç
        # set edilmemiş (varsayılan boş string) kalmış — services/
        # belief_engine.py::synthesize SADECE LONG/SHORT/WAIT anahtarlı
        # bir cluster_votes dict'i bekliyor, boş/geçersiz bir direction
        # KeyError ile çöküyor. Fail-closed: geçersiz oy sessizce atlanır.
        if opinion.direction not in ("LONG", "SHORT", "WAIT"):
            continue
        opinions.append(opinion)
    return opinions


def _resynthesize_with_domain_excluded(agent_contributions: list[dict], excluded_domain: str):
    """excluded_domain'in oyu SIFIRLANMIŞ halde belief-fusion'ı yeniden
    çalıştırır (services/belief_engine.py::synthesize — gerçek, canlıda
    kullanılan AYNI pure fonksiyon). excluded_domain bu kararda hiç oy
    kullanmamışsa (ör. data_unavailable_domains'teydi) None döner —
    ablation anlamsız, zorla bir sonuç üretilmez. compute_leave_one_out_
    impact ve compute_leave_one_out_counterfactual_direction'ın PAYLAŞTIĞI
    tek yeniden-sentezleme adımı — iki fonksiyon arasında sürüklenme
    riski olmasın diye."""
    opinions = reconstruct_opinions(agent_contributions)
    if not opinions:
        return None
    return synthesize_with_domain_excluded(opinions, excluded_domain)


def synthesize_with_domain_excluded(opinions: list[AgentOpinion], excluded_domain: str):
    """Faz 368 — kullanıcı isteği: analytics/pivotal_agent_sizing_gate.py
    CANLI bir karar döngüsünde (henüz agent_contributions'a serileştirilip
    kaydedilmemiş, elde zaten list[AgentOpinion] varken) "bu domain
    OLMASAYDI şu anki karar ne olurdu" sorusunu sormak istiyor —
    _resynthesize_with_domain_excluded'in dict->reconstruct_opinions
    adımı burada GEREKSIZ bir round-trip olurdu. Alt seviye ortak adım
    buraya çıkarıldı, _resynthesize_with_domain_excluded (geçmiş/
    kaydedilmiş kararlar için) ÜSTÜNE ince bir sarmalayıcı oldu — davranış
    DEĞİŞMEDİ, sadece paylaşılıyor."""
    return synthesize_with_domains_excluded(opinions, {excluded_domain})


def synthesize_with_domains_excluded(opinions: list[AgentOpinion], excluded_domains: set[str]):
    """Faz 368-devam — kullanıcı kararı: GPT'nin "Agent Interaction" önerisi
    ("A+B birlikte yokken ne olur?") tek-domain leave-one-out'un ötesine
    geçiyor. synthesize_with_domain_excluded'in genelleştirilmiş hali —
    BİRDEN ÇOK domain'in oyu aynı anda SIFIRLANMIŞ halde belief-fusion'ı
    yeniden çalıştırır. excluded_domains'teki HİÇBİR domain bu kararda oy
    kullanmamışsa None (ablation anlamsız). Tek-domain çağrısı (yukarıdaki
    fonksiyon) davranışı DEĞİŞMEDİ — ona sadece {excluded_domain} ile
    delege ediyor."""
    from services.belief_engine import BeliefEngine

    if not any(o.domain.value in excluded_domains for o in opinions):
        return None

    adjusted = []
    for o in opinions:
        if o.domain.value in excluded_domains:
            o = o.model_copy(deep=True)
            o.performance_weight = 0.0
            o.recalculate()
        adjusted.append(o)

    return BeliefEngine().synthesize(adjusted)


def resynthesize_belief_and_opinions_with_domain_excluded(
    agent_contributions: list[dict], excluded_domain: str,
):
    """Faz 363 — services/counterfactual_agent_impact_gatherer.py'nin
    ihtiyacı: SADECE karşı-olgusal Belief değil, RiskTargetStage/
    DecisionFusion'ın da girdi olarak istediği AYARLANMIŞ (excluded_
    domain sıfırlanmış) opinions listesinin kendisi. _resynthesize_
    with_domain_excluded ile AYNI hesap — sadece iki parçayı da (belief,
    opinions) dışarı veriyor. excluded_domain hiç oy kullanmamışsa None."""
    from services.belief_engine import BeliefEngine

    opinions = reconstruct_opinions(agent_contributions)
    if not opinions:
        return None
    if not any(o.domain.value == excluded_domain for o in opinions):
        return None

    adjusted = []
    for o in opinions:
        if o.domain.value == excluded_domain:
            o = o.model_copy(deep=True)
            o.performance_weight = 0.0
            o.recalculate()
        adjusted.append(o)

    return BeliefEngine().synthesize(adjusted), adjusted


def compute_leave_one_out_impact(
    agent_contributions: list[dict],
    excluded_domain: str,
    actual_direction: str,
) -> str | None:
    """Tek bir gerçek kapanmış kararı, excluded_domain'in oyu SIFIRLANMIŞ
    halde yeniden sentezler. Döner: "caused_trade" (karşı-olgusal WAIT'e
    düştü — bu ajan olmasaydı yönlü bir belief bile oluşmazdı),
    "flipped_direction" (karşı-olgusal hâlâ yönlü ama GERÇEKLEŞENDEN
    farklı), "not_pivotal" (karşı-olgusal gerçekleşenle AYNI)."""
    counterfactual = _resynthesize_with_domain_excluded(agent_contributions, excluded_domain)
    if counterfactual is None:
        return None
    if counterfactual.direction == "WAIT":
        return "caused_trade"
    if counterfactual.direction != actual_direction:
        return "flipped_direction"
    return "not_pivotal"


def compute_leave_one_out_counterfactual_direction(
    agent_contributions: list[dict],
    excluded_domain: str,
    actual_direction: str,
) -> str | None:
    """Faz 363 — kullanıcı isteği: compute_leave_one_out_impact SADECE bir
    kategori ETİKETİ ("flipped_direction") döndürüyor, gerçek karşı-
    olgusal YÖNÜ (LONG/SHORT) hiç dışarı vermiyordu — bu yüzden "bu ajan
    olmasaydı hangi işlem açılırdı" sorusuna cevap veren bir karşı-
    olgusal replay için kullanılamıyordu. Bu fonksiyon SADECE gerçek bir
    yön-değişimi (flipped_direction) durumunda o YENİ yönü (LONG/SHORT)
    döndürür; caused_trade (WAIT'e düştü, replay edilecek yönlü bir
    işlem yok) ya da not_pivotal (zaten aynı) durumlarında None döner —
    mevcut compute_leave_one_out_impact'in kategorizasyon mantığı
    HİÇ DEĞİŞMEDİ, bu sadece onun ürettiği bilgiyi tam olarak açığa
    çıkaran ince bir sarmalayıcı."""
    counterfactual = _resynthesize_with_domain_excluded(agent_contributions, excluded_domain)
    if counterfactual is None:
        return None
    if counterfactual.direction in ("WAIT", actual_direction):
        return None
    return counterfactual.direction


MIN_SAMPLES_FOR_WIN_RATE = 10


def summarize_ablation_by_domain(records: list[dict]) -> dict:
    """records: her biri {'domain', 'impact', 'pnl'} olan GERÇEK
    sonuçlar (compute_leave_one_out_impact'in her gerçek karar için
    ürettiği). Domain başına: kaç kararda oy kullandı, kaçında
    "caused_trade" (o kararların TOPLAM gerçek pnl'i — bu ajan
    olmasaydı bu kâr/zarar HİÇ gerçekleşmezdi, gerçek bir nedensel
    atıf) ve kaçında "flipped_direction" (sadece sayım, pnl atfedilmiyor)
    oldu.

    Faz 298 — kullanıcı isteği: "minimum evidence gate'leri karar
    eşiğiyle daha sıkı hizalanmalı." caused_trade_total_pnl (toplam
    gerçek nedensel katkı, KESİN bir para tutarı) her zaman raporlanıyor
    — ama caused_trade_win_rate (bir ORAN) örneklem küçükken (ör. n=8
    ile "%100") yanıltıcı kesinlik izlenimi verebiliyordu. WeightOptimizer/
    SourceReliabilityAgent'ın zaten kullandığı AYNI MIN_SAMPLES=10
    eşiğiyle hizalandı — altında fail-closed None (icat edilmiş bir
    güven aralığı değil, sadece "henüz yeterli kanıt yok")."""
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_domain[r["domain"]].append(r)

    summary = {}
    for domain, domain_records in by_domain.items():
        caused = [r for r in domain_records if r["impact"] == "caused_trade"]
        flipped = [r for r in domain_records if r["impact"] == "flipped_direction"]
        caused_wins = sum(1 for r in caused if r["pnl"] > 0)
        has_enough_samples = len(caused) >= MIN_SAMPLES_FOR_WIN_RATE
        summary[domain] = {
            "votes_cast": len(domain_records),
            "caused_trade_count": len(caused),
            "caused_trade_total_pnl": round(sum(r["pnl"] for r in caused), 4),
            "caused_trade_win_rate": round(caused_wins / len(caused), 4) if has_enough_samples else None,
            # Faz 304 — Collective Intelligence'ta uygulanan AYNI desen
            # (analytics/collective_intelligence.py::compute_accuracy_
            # confidence_interval): MIN_SAMPLES_FOR_WIN_RATE eşiği win_rate'i
            # tamamen gizleyip göstermeyi belirliyor ama n=10 civarında bile
            # nokta tahmini hâlâ geniş bir bant içinde belirsiz olabilir —
            # %95 Wilson aralığı nokta tahminin yanına bilgilendirme amaçlı
            # ekleniyor, hiçbir eşiği/kararı değiştirmiyor.
            "caused_trade_win_rate_ci": (
                compute_accuracy_confidence_interval(caused_wins, len(caused)) if has_enough_samples else None
            ),
            "flipped_direction_count": len(flipped),
            "not_pivotal_count": len(domain_records) - len(caused) - len(flipped),
            # Faz 368 — GPT dış rapor önerisi (kullanıcı isteği): mutlak
            # caused_trade_total_pnl tek başına yanıltıcı — order_flow'un
            # 50 caused_trade'de ürettiği toplam, macro'nun 576 caused_
            # trade'de ürettiğinden daha KÜÇÜK olabilir ama İŞLEM BAŞINA
            # çok daha güçlü olabilir. caused_trade_expectancy (işlem
            # başına ortalama pnl) bu iki boyutu ayırıyor. caused_trade_
            # rate (bu domain'in TÜM oylarının ne kadarının gerçekten
            # pivot olduğu) "geniş bağlam sağlayıcı" (yüksek rate, orta
            # expectancy) ile "seçici güçlü tetikleyici" (düşük rate,
            # yüksek expectancy) rollerini ayırt etmeye yarıyor.
            "caused_trade_expectancy": (
                round(sum(r["pnl"] for r in caused) / len(caused), 4) if caused else None
            ),
            "caused_trade_rate": round(len(caused) / len(domain_records), 4) if domain_records else 0.0,
        }
    return summary


def _resynthesize_with_domains_excluded(agent_contributions: list[dict], excluded_domains: set[str]):
    """_resynthesize_with_domain_excluded'in çoklu-domain hali —
    synthesize_with_domains_excluded'e AYNI dict->reconstruct_opinions
    hazırlığını yapar."""
    opinions = reconstruct_opinions(agent_contributions)
    if not opinions:
        return None
    return synthesize_with_domains_excluded(opinions, excluded_domains)


def compute_pairwise_ablation_interaction(
    agent_contributions: list[dict],
    domain_a: str,
    domain_b: str,
    actual_direction: str,
) -> dict | None:
    """Faz 368-devam — GPT'nin "Agent Interaction" önerisi: tek-domain
    leave-one-out ("A olmasaydı ne olurdu") A ile B arasındaki İLİŞKİYİ
    hiç sormuyor. Bu fonksiyon AYNI gerçek kapanmış kararı üç farklı
    karşı-olgusal durumda yeniden sentezler: SADECE A çıkarılmış (B hâlâ
    oy veriyor), SADECE B çıkarılmış (A hâlâ oy veriyor), ve İKİSİ BİRDEN
    çıkarılmış. domain_a veya domain_b bu kararda hiç oy kullanmamışsa
    None (ablation anlamsız — ikisi de gerçekten oy vermiş olmalı).

    Döner: {"a_alone_impact", "b_alone_impact", "both_removed_impact"} —
    her biri compute_leave_one_out_impact'in AYNI üç kategorisi
    ("caused_trade"/"flipped_direction"/"not_pivotal"). classify_pairwise_
    relationship bu üçlüyü tek bir ilişki etiketine indirger."""
    opinions = reconstruct_opinions(agent_contributions)
    present_domains = {o.domain.value for o in opinions}
    if domain_a not in present_domains or domain_b not in present_domains:
        return None

    def _classify(counterfactual) -> str:
        if counterfactual.direction == "WAIT":
            return "caused_trade"
        if counterfactual.direction != actual_direction:
            return "flipped_direction"
        return "not_pivotal"

    without_a = synthesize_with_domains_excluded(opinions, {domain_a})
    without_b = synthesize_with_domains_excluded(opinions, {domain_b})
    without_both = synthesize_with_domains_excluded(opinions, {domain_a, domain_b})

    return {
        "a_alone_impact": _classify(without_a),
        "b_alone_impact": _classify(without_b),
        "both_removed_impact": _classify(without_both),
    }


def classify_pairwise_relationship(a_alone_impact: str, b_alone_impact: str, both_removed_impact: str) -> str:
    """compute_pairwise_ablation_interaction'ın üç kategorisini TEK bir
    ilişki etiketine indirger — GPT'nin önerdiği "A+B varken/A tek/B
    tek/hiçbiri yokken ne olur" 2x2 karşılaştırmasının nedensel (sadece
    korelasyonel değil, gerçek karşı-olgusal replay'e dayanan) versiyonu:

    - "redundant_substitutes": NE A NE B tek başına pivotal değil, ama
      İKİSİ BİRDEN çıkınca sonuç değişiyor — birbirinin yerini tutuyorlar
      (biri varken diğeri "gereksiz" görünüyor, ama ikisi de yoksa boşluk
      kapanmıyor). Feature Intelligence Layer'ın redundancy kavramının
      nedensel karşılığı.
    - "both_independently_pivotal": HEM A HEM B tek başına bile pivotal —
      birbirinden bağımsız, ikisi de gerçek/ayrı bilgi taşıyor.
    - "a_dominates" / "b_dominates": SADECE biri tek başına pivotal,
      diğerinin varlığı/yokluğu sonucu hiç değiştirmiyor.
    - "jointly_irrelevant": üçü de "not_pivotal" — bu ikili bu kararda
      hiçbir şekilde belirleyici değil."""
    a_pivotal = a_alone_impact != "not_pivotal"
    b_pivotal = b_alone_impact != "not_pivotal"
    both_pivotal = both_removed_impact != "not_pivotal"

    if a_pivotal and b_pivotal:
        return "both_independently_pivotal"
    if not a_pivotal and not b_pivotal:
        return "redundant_substitutes" if both_pivotal else "jointly_irrelevant"
    return "a_dominates" if a_pivotal else "b_dominates"


def summarize_pairwise_ablation_by_domain_pair(records: list[dict]) -> dict:
    """records: her biri {'pair': 'a|b' (alfabetik sıralı), 'relationship',
    'both_removed_pnl'} olan GERÇEK sonuçlar (compute_pairwise_ablation_
    interaction + classify_pairwise_relationship'in her gerçek karar için
    ürettiği, sadece both_removed_impact=='caused_trade' olan kararlarda
    pnl atfedilir — tek-domain summarize_ablation_by_domain'in AYNI
    disiplini). Çift başına: kaç kararda ikisi de oy kullandı, ilişki
    türü dağılımı, ve substitution_rate (kaçının "redundant_substitutes"
    çıktığı — A ile B'nin ne sıklıkla birbirinin yerini tuttuğu)."""
    by_pair: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_pair[r["pair"]].append(r)

    summary = {}
    for pair, pair_records in by_pair.items():
        n = len(pair_records)
        redundant = [r for r in pair_records if r["relationship"] == "redundant_substitutes"]
        both_pivotal = [r for r in pair_records if r["relationship"] == "both_independently_pivotal"]
        a_dominates = [r for r in pair_records if r["relationship"] == "a_dominates"]
        b_dominates = [r for r in pair_records if r["relationship"] == "b_dominates"]
        irrelevant = [r for r in pair_records if r["relationship"] == "jointly_irrelevant"]
        summary[pair] = {
            "n_both_voted": n,
            "redundant_substitutes_count": len(redundant),
            "substitution_rate": round(len(redundant) / n, 4) if n else 0.0,
            "both_independently_pivotal_count": len(both_pivotal),
            "a_dominates_count": len(a_dominates),
            "b_dominates_count": len(b_dominates),
            "jointly_irrelevant_count": len(irrelevant),
            "redundant_substitutes_total_pnl": round(sum(r["both_removed_pnl"] for r in redundant), 4),
        }
    return summary
