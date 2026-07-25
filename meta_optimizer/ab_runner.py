"""A/B test motoru — Bonferroni düzeltmeli."""
import json
import math
from datetime import datetime
from pathlib import Path


class ABTestRunner:
    def __init__(self, prompt_a: str, prompt_b: str, min_sample: int = 100):
        self.prompt_a = prompt_a
        self.prompt_b = prompt_b
        self.min_sample = min_sample
        self.results_a: list[dict] = []
        self.results_b: list[dict] = []
        self.is_active = False
        self.trade_count = 0
        self._test_counter = self._load_test_counter()

    def _load_test_counter(self) -> int:
        path = Path("ab_test_counter.json")
        if path.exists():
            return json.loads(path.read_text()).get("count", 0)
        return 0

    def _save_test_counter(self):
        Path("ab_test_counter.json").write_text(json.dumps({"count": self._test_counter}))

    def start(self):
        self.is_active = True
        self.trade_count = 0
        self.results_a.clear()
        self.results_b.clear()

    def record_result(self, variant: str, outcome: dict):
        if variant == "A":
            self.results_a.append(outcome)
        else:
            self.results_b.append(outcome)
        self.trade_count += 1

    def evaluate(self, base_alpha: float = 0.05) -> dict:
        if len(self.results_a) < self.min_sample or len(self.results_b) < self.min_sample:
            return {"verdict": "insufficient_data", "reason": f"Need at least {self.min_sample} trades each"}

        accuracy_a = sum(1 for r in self.results_a if r.get("was_correct", False)) / len(self.results_a)
        accuracy_b = sum(1 for r in self.results_b if r.get("was_correct", False)) / len(self.results_b)
        improvement = accuracy_b - accuracy_a

        self._test_counter += 1
        self._save_test_counter()
        adjusted_alpha = base_alpha / self._test_counter

        n_a, n_b = len(self.results_a), len(self.results_b)
        p_pool = (sum(1 for r in self.results_a if r.get("was_correct", False)) +
                  sum(1 for r in self.results_b if r.get("was_correct", False))) / (n_a + n_b)
        se = math.sqrt(p_pool * (1 - p_pool) * (1/n_a + 1/n_b))
        z_score = improvement / se if se > 0 else 0.0
        p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(z_score) / math.sqrt(2))))

        if p_value < adjusted_alpha and improvement > 0:
            verdict = "accept_b"
            reason = f"Prompt B significantly better (p={p_value:.4f} < {adjusted_alpha:.4f})"
        elif improvement > 0.05:
            verdict = "promising_but_not_significant"
            reason = f"Improvement {improvement:.1%} but not significant (p={p_value:.4f})"
        else:
            verdict = "no_significant_difference"
            reason = f"Δ={improvement:.1%}, p={p_value:.4f}"

        return {
            "verdict": verdict, "reason": reason,
            "accuracy_a": accuracy_a, "accuracy_b": accuracy_b,
            "improvement": improvement, "p_value": p_value,
            "adjusted_alpha": adjusted_alpha, "test_number": self._test_counter,
            "timestamp": datetime.now().isoformat(),
        }

    def save_results(self, path: str = "ab_test_results.json"):
        with open(Path(path), "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "prompt_a": self.prompt_a,
                "prompt_b": self.prompt_b,
                "evaluation": self.evaluate(),
            }, f, indent=2)
