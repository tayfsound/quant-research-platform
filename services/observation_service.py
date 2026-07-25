"""Observation Service — ham veriden gözlem üretir."""
from contracts.knowledge import KnowledgeCategory, KnowledgeEntry
from contracts.observation import Observation, ObservationType
from services.knowledge_service import KnowledgeService


class ObservationService:
    def __init__(self, knowledge: KnowledgeService):
        self.knowledge = knowledge
        self._observations: list[Observation] = []

    def record(self, obs: Observation) -> Observation:
        self._observations.append(obs)
        self.knowledge.record(KnowledgeEntry(
            category=KnowledgeCategory.OBSERVATION,
            symbol=obs.symbol,
            timeframe=obs.timeframe,
            conditions={"type": obs.type, "expression": obs.expression},
            result=obs.data,
            source="observation_service",
        ))
        return obs

    def query(self, symbol: str | None = None, obs_type: ObservationType | None = None) -> list[Observation]:
        results = self._observations
        if symbol:
            results = [o for o in results if o.symbol == symbol]
        if obs_type:
            results = [o for o in results if o.type == obs_type]
        return results

    def detect_anomalies(self, symbol: str, lookback: int = 100) -> list[Observation]:
        """İstatistiksel anomali tespiti — basit eşik tabanlı."""
        recent = self.query(symbol=symbol)[-lookback:]
        anomalies = []
        # Örnek: RSI < 20 veya > 80
        for obs in recent:
            rsi = obs.data.get("rsi", 50)
            if rsi < 20 or rsi > 80:
                anomalies.append(obs)
        return anomalies
