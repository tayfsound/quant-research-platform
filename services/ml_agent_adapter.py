"""ML Prediction -> AgentOpinion adapter."""

from contracts.agent import AgentDomain, AgentOpinion
from contracts.ml import Direction, PredictionResult


class MLAgentAdapter:
    """
    ML modellerinden gelen tahminleri
    Cognitive Council'in anlayacağı AgentOpinion formatına çevirir.
    """

    def to_opinion(
        self,
        prediction: PredictionResult,
    ) -> AgentOpinion:

        direction_map = {
            Direction.LONG: "LONG",
            Direction.SHORT: "SHORT",
            Direction.NEUTRAL: "WAIT",
        }

        evidence = [
            f"model_version={prediction.model_version}",
            f"model_id={prediction.model_id}",
            f"confidence={prediction.confidence}",
        ]

        if prediction.raw_output:
            evidence.append(
                f"raw_output={prediction.raw_output}"
            )

        if prediction.explainability:
            evidence.append(
                f"explainability={prediction.explainability}"
            )

        opinion = AgentOpinion(
            agent_id=f"ml:{prediction.model_version}",
            domain=AgentDomain.QUANT,
            direction=direction_map[prediction.direction],
            confidence=prediction.confidence,
            data_quality=0.8,
            evidence_strength=0.7,
            freshness=1.0,
            source_reliability=0.8,
            evidence=evidence,
        )

        opinion.recalculate()

        return opinion
