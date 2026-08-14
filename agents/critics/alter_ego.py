"""Alter Ego Challenger — bilişsel önyargı denetimi (self-critique layer).

`services/agent_debate.py::_run_cognitive_audit()` bu rolü zaten bekliyordu
(`self.challengers.get(AgentDomain.ALTER_EGO.value)`) ama hiçbir yerde
register edilmediği için hep `None` dönüyordu, `CognitiveAudit` hep boş/
varsayılan kalıyordu. Bu, "psychology"/"behavioral" domain'lerinin gerçek
karşılığı — ayrı, Sentiment ile çakışan birer oy-ajanı değil, council'in
KENDİ davranışını (herd behavior, overconfidence, confirmation bias)
eleştiren bir denetim katmanı.

`_run_cognitive_audit()`, dönen `AgentChallenge.reason` metnindeki
"yanlılık"/"sürü"/"güven" kelimelerine göre skorları CognitiveAudit'e
dağıtıyor — bu yüzden reason metinleri bilinçli olarak bu kelimeleri içeriyor.
"""
from contracts.agent import AgentChallenge, AgentDomain, AgentOpinion


class AlterEgoChallenger:
    def __init__(self):
        self.domain = AgentDomain.ALTER_EGO

    def challenge(self, opinion: AgentOpinion, context: dict) -> list[AgentChallenge]:
        opinions_data = context.get("opinions", [])
        rounds_data = context.get("rounds", [])
        challenges: list[AgentChallenge] = []

        if not opinions_data:
            return challenges

        directional = [o for o in opinions_data if o.get("direction") != "WAIT"]
        confidences = [o.get("confidence", 0.0) for o in opinions_data]
        evidence_strengths = [o.get("evidence_strength", 0.5) for o in opinions_data]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        avg_evidence_strength = sum(evidence_strengths) / len(evidence_strengths) if evidence_strengths else 0.5

        majority_share = 0.0
        if directional:
            counts: dict[str, int] = {}
            for o in directional:
                counts[o["direction"]] = counts.get(o["direction"], 0) + 1
            majority_share = max(counts.values()) / len(directional)

        # Herd behavior: neredeyse herkes aynı yönde, gerçek çeşitlilik yok.
        if directional and majority_share >= 0.75 and len(directional) >= 3:
            challenges.append(AgentChallenge(
                challenger_domain=AgentDomain.ALTER_EGO,
                target_domain=AgentDomain.EXECUTIVE,
                reason=f"Sürü davranışı riski: yönlü ajanların %{majority_share:.0%}'i aynı yönde hemfikir",
                confidence=round(majority_share, 3),
                evidence_strength=0.7,
                suggested_adjustment="Pozisyon büyüklüğünü azalt — bağımsız görüş çeşitliliği düşük",
            ))

        # Overconfidence: ortalama güven yüksek ama destekleyen kanıt zayıf.
        if avg_confidence > 0.75 and avg_evidence_strength < 0.5:
            challenges.append(AgentChallenge(
                challenger_domain=AgentDomain.ALTER_EGO,
                target_domain=AgentDomain.EXECUTIVE,
                reason=f"Aşırı güven riski: ortalama güven {avg_confidence:.2f} olmasına rağmen ortalama kanıt gücü zayıf ({avg_evidence_strength:.2f})",
                confidence=round(min(avg_confidence, 0.9), 3),
                evidence_strength=avg_evidence_strength,
                suggested_adjustment="Kanıt gücü iyileşene kadar güveni indirimle değerlendir",
            ))

        # Confirmation bias: neredeyse oybirliği var AMA debate turlarında
        # HİÇBİR itiraz üretilmemiş — kimse gerçekten karşı görüş sormamış.
        total_challenges_in_rounds = sum(len(r.get("challenges", [])) for r in rounds_data)
        if directional and majority_share >= 0.75 and total_challenges_in_rounds == 0:
            challenges.append(AgentChallenge(
                challenger_domain=AgentDomain.ALTER_EGO,
                target_domain=AgentDomain.EXECUTIVE,
                reason="Doğrulama yanlılığı riski: neredeyse oybirliğine rağmen tartışma sırasında hiç gerçek itiraz üretilmedi",
                confidence=round(majority_share, 3),
                evidence_strength=0.6,
                suggested_adjustment="Harekete geçmeden önce aktif olarak karşı kanıt ara",
            ))

        return challenges
