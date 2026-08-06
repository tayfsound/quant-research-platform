"""Metacognition Layer — DecisionReason tipleriyle."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import DecisionReason

RISK_WEIGHTS = {
    "high_volatility": 0.10,
    "direction_conflict": 0.30,
    "low_volume": 0.05,
    "regime_change": 0.20,
    "memory_weak": 0.15,
}

class Metacognition:
    def __init__(self, act_threshold: float = 0.7, reduce_threshold: float = 0.4):
        self.act_threshold = act_threshold
        self.reduce_threshold = reduce_threshold
        self.history: list[dict] = []

    def evaluate_confidence(
        self,
        ctx: CognitiveCycleContext,
        criticism: dict,
        contradiction: dict,
        belief_strength: float = 0.5,
    ) -> dict:
        # Gerçek bulgu: model_confidence şu ana kadar SADECE hafızadan
        # geliyordu — hafıza yoksa (ki bu genç bir sistemde hemen her
        # zaman böyle) sabit 0.5'e düşüp sadece risk_penalty ile aşağı
        # iniyordu. Council'in bu cycle'da GERÇEKTEN ne kadar güçlü/
        # tutarlı bir konsensüse vardığı (belief.strength — services/
        # belief_engine.py'de gerçek, ağırlıklı oy gücünden hesaplanıyor)
        # hiç kullanılmıyordu. Yani 9 ajan bile birleşse confidence hâlâ
        # ~0.5'ten başlayıp ACT eşiğine (0.7) asla ulaşamıyordu — sistemin
        # neredeyse hep WAIT üretmesinin asıl kök nedeni buydu.
        memory_insights = [
            item for item in ctx.cognition.relevant_knowledge
            if item.get("type") == "memory_insight"
        ]

        model_confidence = belief_strength
        if memory_insights:
            memory_confidence = memory_insights[-1]["data"].get("confidence", 0.5)
            # İkisinden güçlü olanı esas alınır — ne çok güçlü bir hafıza
            # desteği (geçmişte benzer durumda haklı çıkmış), ne de bu
            # cycle'ın çok güçlü/tutarlı bir Council konsensüsü, diğeriyle
            # seyreltilerek zayıflatılmamalı.
            model_confidence = max(model_confidence, memory_confidence)

        risk_flags = criticism.get("risk_flags", [])
        risk_penalty = sum(RISK_WEIGHTS.get(flag, 0.1) for flag in risk_flags)
        conflict_level = contradiction.get("conflict_level", 0.0)

        # Çok kaynaklı güven hesabı
        confidence = model_confidence - risk_penalty - (conflict_level * 0.2)
        confidence = max(0.0, min(1.0, confidence))

        # Eskiden 1 - memory_confidence idi (hafıza yoksa UnboundLocalError
        # riskiyle) — artık 1 - model_confidence: hafıza YA DA gerçek
        # belief_strength, hangisi kullanıldıysa onu yansıtıyor.
        uncertainty = max(conflict_level, 1 - model_confidence)

        if confidence >= self.act_threshold:
            decision = "ACT"
        elif confidence >= self.reduce_threshold:
            decision = "REDUCE"
        else:
            decision = "WAIT"

        # DecisionReason belirle
        reason = self._determine_reason(decision, confidence, memory_insights, risk_flags)

        self.history.append({
            "confidence": confidence,
            "uncertainty": uncertainty,
            "decision": decision,
            "reason": reason,
        })

        return {
            "confidence": round(confidence, 3),
            "uncertainty": round(uncertainty, 3),
            "decision": decision,
            "reason": reason.value if isinstance(reason, DecisionReason) else reason,
            "reason_text": self._generate_reason(decision, confidence, risk_flags),
        }

    def _determine_reason(
        self, decision: str, confidence: float,
        memory_insights: list, risk_flags: list[str]
    ) -> DecisionReason:
        if not memory_insights:
            return DecisionReason.INSUFFICIENT_DATA
        if len(risk_flags) >= 2:
            return DecisionReason.HIGH_RISK
        if confidence < self.reduce_threshold:
            return DecisionReason.LOW_CONFIDENCE
        if decision == "WAIT":
            return DecisionReason.NO_SIGNAL
        if memory_insights and confidence > self.act_threshold:
            return DecisionReason.MEMORY_SUPPORTED
        return DecisionReason.STRONG_SIGNAL

    def _generate_reason(self, decision: str, confidence: float, risk_flags: list[str]) -> str:
        if decision == "WAIT":
            return f"Confidence {confidence:.2f} too low — waiting"
        elif decision == "REDUCE":
            return f"Moderate confidence {confidence:.2f} — reducing"
        elif risk_flags:
            return f"Acting with {len(risk_flags)} risk flag(s)"
        return "High confidence — strong memory support"

    def get_track_record(self) -> dict:
        if not self.history:
            return {"total": 0, "accuracy": 0.0}
        total = len(self.history)
        correct = sum(1 for h in self.history if h.get("was_correct", False))
        return {"total": total, "accuracy": round(correct / total, 3) if total > 0 else 0.0}
