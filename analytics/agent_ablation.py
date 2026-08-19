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


def compute_leave_one_out_impact(
    agent_contributions: list[dict],
    excluded_domain: str,
    actual_direction: str,
) -> str | None:
    """Tek bir gerçek kapanmış kararı, excluded_domain'in oyu SIFIRLANMIŞ
    halde yeniden sentezler (services/belief_engine.py::synthesize —
    gerçek, canlıda kullanılan AYNI pure fonksiyon). excluded_domain bu
    kararda hiç oy kullanmamışsa (ör. data_unavailable_domains'teydi)
    None döner — ablation anlamsız, zorla bir sonuç üretilmez.

    Döner: "caused_trade" (karşı-olgusal WAIT'e düştü — bu ajan
    olmasaydı yönlü bir belief bile oluşmazdı), "flipped_direction"
    (karşı-olgusal hâlâ yönlü ama GERÇEKLEŞENDEN farklı), "not_pivotal"
    (karşı-olgusal gerçekleşenle AYNI)."""
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

    counterfactual = BeliefEngine().synthesize(adjusted)
    if counterfactual.direction == "WAIT":
        return "caused_trade"
    if counterfactual.direction != actual_direction:
        return "flipped_direction"
    return "not_pivotal"


def summarize_ablation_by_domain(records: list[dict]) -> dict:
    """records: her biri {'domain', 'impact', 'pnl'} olan GERÇEK
    sonuçlar (compute_leave_one_out_impact'in her gerçek karar için
    ürettiği). Domain başına: kaç kararda oy kullandı, kaçında
    "caused_trade" (o kararların TOPLAM gerçek pnl'i — bu ajan
    olmasaydı bu kâr/zarar HİÇ gerçekleşmezdi, gerçek bir nedensel
    atıf) ve kaçında "flipped_direction" (sadece sayım, pnl atfedilmiyor)
    oldu."""
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_domain[r["domain"]].append(r)

    summary = {}
    for domain, domain_records in by_domain.items():
        caused = [r for r in domain_records if r["impact"] == "caused_trade"]
        flipped = [r for r in domain_records if r["impact"] == "flipped_direction"]
        caused_wins = sum(1 for r in caused if r["pnl"] > 0)
        summary[domain] = {
            "votes_cast": len(domain_records),
            "caused_trade_count": len(caused),
            "caused_trade_total_pnl": round(sum(r["pnl"] for r in caused), 4),
            "caused_trade_win_rate": round(caused_wins / len(caused), 4) if caused else None,
            "flipped_direction_count": len(flipped),
            "not_pivotal_count": len(domain_records) - len(caused) - len(flipped),
        }
    return summary
