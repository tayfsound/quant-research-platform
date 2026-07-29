"""Training Sample Quality Scorer — Eğitim örneklerinin kalitesini puanlar."""
from typing import Any
from contracts.decision_event import DecisionEvent

class SampleQualityScorer:
    def __init__(self):
        pass

    def score_sample(self, event: DecisionEvent) -> dict[str, Any]:
        """Bir DecisionEvent'in eğitim için kalite puanını hesaplar."""
        scores = {}
        
        # 1. Data Completeness Score (0.0 - 1.0)
        # Gerekli alanların varlığı kontrol edilir
        completeness = 1.0
        market_snapshot = event.market_snapshot or {}
        if not market_snapshot.get("features"): completeness -= 0.3
        if not event.agent_opinions: completeness -= 0.3
        if not event.outcome: completeness -= 0.4
        scores["completeness_score"] = max(0.0, completeness)

        # 2. Confidence Reliability (0.0 - 1.0)
        # Yüksek güvenle verilen ama yanlış çıkan kararların gürültü puanı
        # Düşük güvenli kararlar eğitim için daha az değerli olabilir
        confidence = event.confidence
        scores["confidence_value"] = confidence

        # 3. Informational Value (Surprise Factor)
        # Ajanlar arasında büyük fikir ayrılığı varsa bu örnek daha öğreticidir
        opinions = event.agent_opinions
        if opinions:
            confidences = [o.get("confidence", 0.0) for o in opinions]
            std_conf = float((sum((c - sum(confidences)/len(confidences))**2 for c in confidences) / len(confidences))**0.5) if len(confidences) > 1 else 0.0
            scores["disagreement_value"] = std_conf
        else:
            scores["disagreement_value"] = 0.0

        # 4. PnL Significance
        # Çok küçük PnL hareketleri gürültü olabilir, büyük hareketler daha değerlidir
        pnl = abs(event.outcome.get("pnl", 0.0)) if event.outcome else 0.0
        scores["significance_score"] = min(1.0, pnl / 10.0) # 10% PnL full significance

        # Final Quality Score Calculation
        # Ağırlıklı ortalama
        final_score = (
            scores["completeness_score"] * 0.4 +
            scores["confidence_value"] * 0.2 +
            scores["disagreement_value"] * 0.2 +
            scores["significance_score"] * 0.2
        )
        scores["final_quality_score"] = round(final_score, 4)
        
        return scores
