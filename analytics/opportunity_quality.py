"""Opportunity Quality / Meta-Labeling — Faz 569-593 (Cognitive Core 2.0).

de Prado'nun meta-labeling ilkesi: birincil modelin (council'in fused
yönü) ÜZERİNE, "bu spesifik sinyale güvenilmeli mi" sorusunu GERÇEKLEŞEN
sonuçlarla cevaplayan ikincil bir katman. Burada kullanılan meta-özellik:
ajan konsensüsü — council'daki ajanların yön oylarındaki (LONG/SHORT/WAIT)
ANLAŞMA derecesi. Ensemble learning'de standart bir bulgu: bağımsız
modeller arasında yüksek anlaşma, tarihsel olarak daha güvenilir
tahminlerle ilişkilidir — icat edilmiş bir ilke değil.

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir pozisyon/risk kararını burada
otomatik değiştirmiyor."""
import math
from collections import defaultdict

from analytics.collective_intelligence import compute_accuracy_confidence_interval

MIN_GROUP_SIZE = 20


def compute_agent_agreement(votes: dict[str, int]) -> float:
    """votes: {'LONG': n, 'SHORT': n, 'WAIT': n} gerçek oy sayıları.
    Normalize edilmiş Shannon entropisinden türetilen anlaşma skoru:
    1.0 = tam anlaşma (tüm oylar tek yönde), 0.0 = maksimum bölünmüşlük
    (oylar tüm kategorilere eşit dağılmış). Oy yoksa (total=0) dürüstçe
    0.0 döner — icat edilmiş bir anlaşma asla üretilmez."""
    total = sum(votes.values())
    if total == 0:
        return 0.0

    probs = [v / total for v in votes.values() if v > 0]
    if len(probs) <= 1:
        return 1.0

    entropy = -sum(p * math.log2(p) for p in probs)
    max_entropy = math.log2(len(votes))
    if max_entropy == 0:
        return 1.0
    return round(max(0.0, 1.0 - (entropy / max_entropy)), 4)


def agreement_from_contributions(contributions: list[dict] | None) -> float | None:
    """GERÇEK kapanmış bir işlemin `decisions.agent_contributions`
    JSON'ından (her ajanın {"domain":..., "direction":...} oyu) LONG/
    SHORT/WAIT sayımı yapıp compute_agent_agreement'a verir. services/
    opportunity_quality_gatherer.py VE services/meta_label_model.py
    (Faz 350 — agent_agreement eğitim özelliği) AYNI çıkarımı paylaşır —
    ikisi bağımsızca tekrarlanırsa train/predict tutarsızlığı riski
    doğar."""
    votes = {"LONG": 0, "SHORT": 0, "WAIT": 0}
    found_any = False
    for item in (contributions or []):
        if not isinstance(item, dict) or "domain" not in item:
            continue
        direction = (item.get("direction") or "").upper()
        if direction in votes:
            votes[direction] += 1
            found_any = True
    if not found_any:
        return None
    return compute_agent_agreement(votes)


def agreement_from_opinions(opinions: list) -> float | None:
    """agreement_from_contributions ile AYNI hesap, ama CANLI karar
    anında (henüz DB'ye yazılmamış) AgentOpinion nesnelerinden — bkz.
    engines/cognitive_pipeline.py::RiskTargetStage. Eğitim (geçmiş
    kapanmış işlemler, contributions dict) ile tahmin (canlı, opinions
    listesi) anında AYNI formülün uygulanması modelin genelleyebilmesi
    için kritik."""
    votes = {"LONG": 0, "SHORT": 0, "WAIT": 0}
    found_any = False
    for o in (opinions or []):
        direction = (getattr(o, "direction", None) or "").upper()
        if direction in votes:
            votes[direction] += 1
            found_any = True
    if not found_any:
        return None
    return compute_agent_agreement(votes)


def _agreement_bucket(agreement: float) -> str:
    if agreement < 0.34:
        return "low"
    if agreement < 0.67:
        return "medium"
    return "high"


def compute_opportunity_quality_by_agreement(
    trades: list[dict],
    min_group_size: int = MIN_GROUP_SIZE,
) -> dict:
    """trades: her biri 'agent_agreement' (compute_agent_agreement'ın
    ürettiği, 0-1 arası) ve 'win' (bool) alanı olan GERÇEK kapanmış
    işlemler. Anlaşma seviyesine (low/medium/high) göre gruplayıp
    win_rate'i karşılaştırır — konsensüsün GERÇEKTEN gerçekleşen
    başarıyla ilişkili olup olmadığını doğrulamak için. min_group_size
    altındaki kovalar fail-closed dışlanır."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        agreement = t.get("agent_agreement")
        if agreement is None or t.get("win") is None:
            continue
        groups[_agreement_bucket(agreement)].append(t)

    results: dict[str, dict] = {}
    for bucket, group_trades in groups.items():
        if len(group_trades) < min_group_size:
            continue
        wins = sum(1 for t in group_trades if t["win"])
        results[bucket] = {
            "sample_size": len(group_trades),
            "win_rate": round(wins / len(group_trades), 4),
            # Faz 305 — Collective Intelligence/Agent Ablation'da uygulanan
            # AYNI desen: min_group_size eşiği win_rate'i tamamen gizleyip
            # göstermeyi belirliyor ama n=20 civarında bile nokta tahmini
            # hâlâ geniş bir bant içinde belirsiz olabilir — %95 Wilson
            # aralığı bilgilendirme amaçlı ekleniyor, hiçbir eşiği/kararı
            # değiştirmiyor.
            "win_rate_ci": compute_accuracy_confidence_interval(wins, len(group_trades)),
        }
    return results
