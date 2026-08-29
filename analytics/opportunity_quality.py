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


# Faz B (2026-08-29) — Feature Intelligence Layer'ın kullanıcı tasarımı:
# ham "kaç ajan anlaştı" (agreement) yerine, anlaşan ajanların GERÇEKTEN
# GÜVENİLİR olup olmadığını da hesaba katan sürekli bir kalite skoru.
# İlke: "9 ajan aynı yönde oy verdi" ile "9 ajan aynı yönde oy verdi VE
# hepsi tarihsel olarak isabetli" AYNI şey değil — birincisi büyük bir
# kalabalığın gürültüsü olabilir, ikincisi gerçek bir kanıt.
def _reliability_from_contributions(
    contributions: list[dict] | None, final_direction: str,
) -> float | None:
    """Nihai yönle AYNI yönde oy veren ajanların GERÇEK source_reliability'
    lerinin (agents/source_reliability_agent.py'nin 20/100/500 pencereli,
    histerezisli hesabı — TEK kaynak, burada YENİDEN hesaplanmıyor, zaten
    her opinion'a gömülü) ortalaması. Anlaşan ajan yoksa ya da hiçbirinin
    source_reliability'si kayıtlı değilse (eski kayıtlar) None — icat
    edilmiş bir "nötr" güvenilirlik asla üretilmez."""
    if final_direction not in ("LONG", "SHORT"):
        return None
    reliabilities = []
    for item in (contributions or []):
        if not isinstance(item, dict) or "domain" not in item:
            continue
        if (item.get("direction") or "").upper() != final_direction:
            continue
        r = item.get("source_reliability")
        if r is not None:
            reliabilities.append(r)
    if not reliabilities:
        return None
    return sum(reliabilities) / len(reliabilities)


def compute_quality_score(agreement: float, mean_reliability: float) -> float:
    """Sürekli kalite skoru: agreement × mean_reliability, ikisi de [0,1]
    aralığında olduğu için çarpım da [0,1] aralığında kalır. Bilinçli
    olarak SADECE iki çarpan — üçüncü bir "feature_independence" çarpanı
    (aynı kararda anlaşan ajanların kaç bağımsız feature'a dayandığı,
    analytics/feature_relationship.py'nin redundancy kümeleriyle
    çapraz-referanslanarak) sağlam bir karar-bazlı hesap gerektiriyor —
    henüz yazılmadı, gelecekteki bir genişleme olarak not düşülüyor,
    icat edilmiş/kırılgan bir yaklaşık değer burada eklenmedi."""
    return round(agreement * mean_reliability, 4)


def _quality_score_bucket(score: float) -> str:
    if score < 0.34:
        return "low"
    if score < 0.67:
        return "medium"
    return "high"


def _profit_factor(pnls: list[float]) -> float | None:
    """Toplam kazanç / |toplam kayıp|. Hiç kayıp yoksa (payda=0) None —
    icat edilmiş bir sonsuz/aşırı büyük sayı asla dönmez."""
    gains = sum(p for p in pnls if p > 0)
    losses = sum(p for p in pnls if p < 0)
    if losses == 0:
        return None
    return round(gains / abs(losses), 4)


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def _summarize_quality_group(group: list[dict]) -> dict:
    wins = sum(1 for t in group if t["win"])
    n = len(group)
    pnls = [t["pnl"] for t in group]
    return {
        "sample_size": n,
        "win_rate": round(wins / n, 4),
        "win_rate_ci": compute_accuracy_confidence_interval(wins, n),
        # Faz B — kullanıcı isteği: win_rate TEK BAŞINA büyüklüğü
        # görmüyor (çok sayıda küçük kazanç + az sayıda dev kayıp aynı
        # win_rate'i verebilir). expectancy (işlem başına ORTALAMA pnl),
        # median_pnl (aşırı uç değerlere daha dayanıklı) ve profit_factor
        # (kazanç/kayıp oranı) bunu tamamlıyor.
        "expectancy": round(sum(pnls) / n, 4),
        "median_pnl": round(_median(pnls), 4),
        "profit_factor": _profit_factor(pnls),
    }


def compute_opportunity_quality_by_score(
    trades: list[dict],
    min_group_size: int = MIN_GROUP_SIZE,
) -> dict:
    """trades: her biri 'quality_score' (compute_quality_score'un ürettiği,
    0-1 arası), 'win' (bool), 'pnl' (float) ve opsiyonel 'market_regime'
    (str) alanı olan GERÇEK kapanmış işlemler. compute_opportunity_
    quality_by_agreement ile AYNI [0.34, 0.67) kova sınırları — ama artık
    ham anlaşma yerine anlaşma×güvenilirlik bileşik skoruna uygulanıyor.

    Döner: {bucket: {"overall": {...}, "by_regime": {regime: {...}}}}.
    "overall" HER ZAMAN min_group_size şartına tabi; "by_regime" alt-
    kırılımları AYRICA kendi min_group_size'larını geçmeli (rejim
    başına örneklem doğal olarak küçülür, fail-closed disiplin aynı)."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        score = t.get("quality_score")
        if score is None or t.get("win") is None or t.get("pnl") is None:
            continue
        groups[_quality_score_bucket(score)].append(t)

    results: dict[str, dict] = {}
    for bucket, group_trades in groups.items():
        if len(group_trades) < min_group_size:
            continue

        by_regime_records: dict[str, list[dict]] = defaultdict(list)
        for t in group_trades:
            regime = t.get("market_regime")
            if regime is not None:
                by_regime_records[regime].append(t)

        by_regime = {
            regime: _summarize_quality_group(regime_trades)
            for regime, regime_trades in by_regime_records.items()
            if len(regime_trades) >= min_group_size
        }

        results[bucket] = {
            "overall": _summarize_quality_group(group_trades),
            "by_regime": by_regime,
        }
    return results


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
