"""Decision Pattern Mining — Karar geçmişlerinden tekrar eden kalıpları çıkarır."""
import json
from pathlib import Path
from typing import Any, Dict, List
from collections import defaultdict

class DecisionPatternMiner:
    def __init__(self, storage_path: str = "decision_logs"):
        self.storage_path = Path(storage_path)
    
    def mine_patterns(self, min_occurrences: int = 3, min_win_rate: float = 0.6) -> List[Dict[str, Any]]:
        """Belirli özellik kombinasyonlarından yüksek win rate'li kalıplar çıkarır."""
        patterns = defaultdict(lambda: {"wins": 0, "losses": 0, "count": 0})
        
        files = list(self.storage_path.glob("decision_*.json"))
        for filename in files:
            try:
                content = json.loads(filename.read_text())
                outcome = content.get("outcome", {})
                if not outcome:
                    continue
                
                belief = content.get("belief", {})
                direction = belief.get("direction", "NEUTRAL")
                confidence = belief.get("confidence", 0.0)
                conf_bucket = "high" if confidence > 0.7 else "low"
                pattern_key = f"{direction}_{conf_bucket}"
                
                pnl = outcome.get("pnl", 0)
                patterns[pattern_key]["count"] += 1
                if pnl > 0:
                    patterns[pattern_key]["wins"] += 1
                else:
                    patterns[pattern_key]["losses"] += 1
            except Exception:
                continue
        
        results = []
        for key, stats in patterns.items():
            if stats["count"] >= min_occurrences:
                win_rate = stats["wins"] / stats["count"]
                if win_rate >= min_win_rate:
                    results.append({
                        "pattern": key,
                        "win_rate": win_rate,
                        "count": stats["count"],
                        "wins": stats["wins"],
                        "losses": stats["losses"]
                    })
        
        return sorted(results, key=lambda x: x["win_rate"], reverse=True)
