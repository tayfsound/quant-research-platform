"""Replay Memory — Eğitim örneklerini saklar ve önceliklendirilmiş örnekleme sağlar."""
import random
import numpy as np
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class ReplaySample(BaseModel):
    decision_id: str
    features: Dict[str, Any]
    label: Any
    quality_score: float = 1.0
    timestamp: str

class ReplayMemory:
    def __init__(self, capacity: int = 10000):
        self.capacity = capacity
        self.memory: List[ReplaySample] = []
        self.position = 0

    def add(self, sample: Dict[str, Any]):
        """Yeni bir örnek ekler. Kapasite dolduğunda en eskiyi siler (circular buffer)."""
        replay_sample = ReplaySample(**sample)
        
        if len(self.memory) < self.capacity:
            self.memory.append(replay_sample)
        else:
            self.memory[self.position] = replay_sample
        
        self.position = (self.position + 1) % self.capacity

    def sample(self, batch_size: int, strategy: str = "uniform") -> List[ReplaySample]:
        """Belirlenen stratejiye göre örneklem alır."""
        if not self.memory:
            return []
        
        actual_batch_size = min(batch_size, len(self.memory))
        
        if strategy == "uniform":
            return random.sample(self.memory, actual_batch_size)
        
        elif strategy == "prioritized":
            # Kalite puanlarına göre olasılık dağılımı oluştur
            scores = np.array([s.quality_score for s in self.memory])
            # Skorların negatif olmamasını sağla ve normalize et
            probs = scores / scores.sum() if scores.sum() > 0 else None
            
            indices = np.random.choice(
                len(self.memory), 
                actual_batch_size, 
                replace=False, 
                p=probs
            )
            return [self.memory[i] for i in indices]
        
        else:
            raise ValueError(f"Unknown sampling strategy: {strategy}")

    def clear(self):
        self.memory = []
        self.position = 0

    def __len__(self):
        return len(self.memory)
