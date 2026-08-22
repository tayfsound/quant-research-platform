"""Contradiction Detector — hipotez ve eleştiri arasındaki çelişkiyi analiz eder."""
from contracts.context import CognitiveCycleContext


class ContradictionDetector:
    def analyze(self, ctx: CognitiveCycleContext, criticism: dict) -> dict:
        """
        Hipotez ve eleştiri arasındaki çelişkiyi değerlendir.
        Dönüş: {
            "conflict_level": float,  # 0-1 arası
            "information_gain": float,
            "recommendation": "PROCEED" | "REDUCE" | "RECONSIDER"
        }
        """
        challenges = len(criticism.get("challenges", []))
        improvements = len(criticism.get("improvements", []))

        # Çelişki seviyesi hesapla
        conflict_level = 0.0
        if "direction_conflict" in criticism.get("risk_flags", []):
            conflict_level += 0.5
        if challenges >= 3:
            conflict_level += 0.3
        elif challenges >= 1:
            conflict_level += 0.15

        # Bilgi kazancı: ne kadar çok yeni bilgi, o kadar değerli
        information_gain = min((challenges + improvements) * 0.2, 1.0)

        # Öneri
        if conflict_level > 0.6:
            recommendation = "RECONSIDER"
        elif conflict_level > 0.3:
            recommendation = "REDUCE"
        else:
            recommendation = "PROCEED"

        return {
            "conflict_level": round(conflict_level, 3),
            "information_gain": round(information_gain, 3),
            "recommendation": recommendation,
        }
