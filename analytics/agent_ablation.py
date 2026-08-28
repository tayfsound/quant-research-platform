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
    from services.belief_engine import BeliefEngine

    if not any(o.domain.value == excluded_domain for o in opinions):
        return None

    adjusted = []
    for o in opinions:
        if o.domain.value == excluded_domain:
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
