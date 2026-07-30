"""Kaynak guvenilirligi ajani — diger ajanlarin guvenilirligini puanlar."""
from typing import Dict, List
from dataclasses import dataclass

@dataclass
class ReliabilityScore:
    domain: str
    source_reliability: float
    data_freshness_hours: float
    source_count: int

class SourceReliabilityAgent:
    def __init__(self):
        self.history: Dict[str, List[float]] = {}
    
    def annotate(self, opinions: List[dict]) -> List[dict]:
        """Her opinion'a source_reliability puanı ekler."""
        for op in opinions:
            domain = op.get("domain", "unknown")
            if domain not in self.history:
                self.history[domain] = []
            
            # Basit: confidence history'si varsa ortalama
            confidence = op.get("confidence", 0.5)
            self.history[domain].append(confidence)
            
            # Reliability = son 10 kararin ortalama confidence'i
            recent = self.history[domain][-10:]
            reliability = sum(recent) / len(recent) if recent else 0.5
            
            op["source_reliability"] = min(reliability, 1.0)
            op["data_freshness_hours"] = 0.0  # Simulated real-time
            op["source_count"] = 1
        
        return opinions
    
    def get_domain_reliability(self, domain: str) -> float:
        scores = self.history.get(domain, [])
        return sum(scores) / len(scores) if scores else 0.5
