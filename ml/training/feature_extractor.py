"""Training Feature Extractor — DecisionEvent'lerden eğitim özellikleri çıkarır."""
from typing import Any

import numpy as np

from contracts.decision_event import DecisionEvent


class TrainingFeatureExtractor:
    def __init__(self):
        pass

    def extract_features(self, event: DecisionEvent) -> dict[str, Any]:
        """Bir DecisionEvent'ten düzleştirilmiş özellik seti çıkarır."""
        features = {}

        # 1. Market Features
        market_snapshot = event.market_snapshot or {}
        market_feats = market_snapshot.get("features", {})
        for k, v in market_feats.items():
            features[f"market_{k}"] = v

        # 2. Agent Consensus Features
        opinions = event.agent_opinions
        if opinions:
            confidences = [o.get("confidence", 0.0) for o in opinions]
            features["agent_avg_confidence"] = float(np.mean(confidences))
            features["agent_std_confidence"] = float(np.std(confidences))

            # Direction mapping
            dir_map = {"LONG": 1, "SHORT": -1, "WAIT": 0, "REDUCE": 0}
            directions = [dir_map.get(o.get("direction", "WAIT"), 0) for o in opinions]
            features["agent_direction_mean"] = float(np.mean(directions))

            # Evidence strength
            evidence_strengths = [o.get("evidence_strength", 0.0) for o in opinions]
            features["agent_avg_evidence_strength"] = float(np.mean(evidence_strengths))

            # FEATURE ENGINEERING: Disagreement / Polarization
            # Yüksek standart sapma ve zıt yönler kutuplaşmayı gösterir
            pos_count = sum(1 for d in directions if d > 0)
            neg_count = sum(1 for d in directions if d < 0)
            features["agent_polarization"] = float(min(pos_count, neg_count) / max(1, pos_count + neg_count))

            # FEATURE ENGINEERING: Weighted Consensus
            # Confidence ile ağırlıklandırılmış yön
            weighted_dir = sum(d * c for d, c in zip(directions, confidences)) / max(1e-6, sum(confidences))
            features["agent_weighted_consensus"] = float(weighted_dir)
        else:
            features["agent_avg_confidence"] = 0.0
            features["agent_std_confidence"] = 0.0
            features["agent_direction_mean"] = 0.0
            features["agent_avg_evidence_strength"] = 0.0
            features["agent_polarization"] = 0.0
            features["agent_weighted_consensus"] = 0.0

        # 3. Belief Features
        belief = event.belief_state or {}
        features["belief_strength"] = belief.get("strength", 0.0)
        features["belief_uncertainty"] = belief.get("uncertainty", 0.0)
        features["belief_entropy"] = belief.get("entropy", 0.0)
        features["belief_disagreement"] = belief.get("cluster_disagreement", 0.0)

        # FEATURE ENGINEERING: Belief-Market Alignment
        # RSI < 30 (aşırı satım) ve belief_strength yüksekse alım fırsatı olabilir
        rsi = market_feats.get("RSI", 50)
        if rsi < 30:
            features["belief_oversold_alignment"] = features["belief_strength"]
        elif rsi > 70:
            features["belief_overbought_alignment"] = features["belief_strength"]
        else:
            features["belief_oversold_alignment"] = 0.0
            features["belief_overbought_alignment"] = 0.0

        # 4. Meta Features
        features["decision_confidence"] = event.confidence
        features["decision_latency"] = event.decision_latency_ms

        # FEATURE ENGINEERING: Confidence Gap
        # Sistem kararı ile ajanların ortalama güveni arasındaki fark
        features["confidence_gap"] = event.confidence - features["agent_avg_confidence"]

        return features

    def extract_label(self, event: DecisionEvent, label_type: str = "pnl") -> Any:
        """Eğitim için etiket çıkarır."""
        if not event.outcome:
            return None

        if label_type == "pnl":
            return event.outcome.get("pnl", 0.0)
        elif label_type == "win":
            return 1 if event.outcome.get("win", False) else 0
        return None
