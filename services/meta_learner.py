"""Meta-Learner — çoklu parametre optimizasyonu, reward tabanlı."""
class MetaLearner:
    def __init__(self):
        self.history: list[dict] = []

    def record_cycle(self, confidence: float, was_correct: bool, reward: float):
        self.history.append({
            "confidence": confidence,
            "was_correct": was_correct,
            "reward": reward,
        })

    def suggest_parameters(self, current: dict, window: int = 50) -> dict:
        """Son N işlem performansına göre tüm parametreleri optimize et."""
        if len(self.history) < window:
            return current
        
        recent = self.history[-window:]
        
        # Act threshold için grid search (reward tabanlı)
        act_candidates = [t / 100 for t in range(40, 91, 5)]  # 0.40, 0.45, ..., 0.90
        best_act = current.get("act_threshold", 0.7)
        best_reward = -999.0
        for t in act_candidates:
            total_reward = 0.0
            for h in recent:
                if h["confidence"] >= t:
                    total_reward += h["reward"]
                # else: işlem yapmama = 0 reward
            if total_reward > best_reward:
                best_reward = total_reward
                best_act = t

        # Reduce threshold: act'ten 0.3 aşağıda (sabit oran)
        best_reduce = max(0.25, best_act - 0.3)

        return {
            "act_threshold": round(current.get("act_threshold", 0.7) * 0.85 + best_act * 0.15, 3),
            "reduce_threshold": round(current.get("reduce_threshold", 0.4) * 0.85 + best_reduce * 0.15, 3),
        }

    def suggest_threshold(self, current: float, window: int = 50) -> float:
        """Geriye uyumlu tek threshold önerisi."""
        params = self.suggest_parameters({"act_threshold": current}, window)
        return params["act_threshold"]
