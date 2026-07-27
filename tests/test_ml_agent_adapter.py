from datetime import datetime
from uuid import uuid4

from contracts.ml import PredictionResult, Direction
from contracts.agent import AgentDomain

from services.ml_agent_adapter import MLAgentAdapter


def test_ml_prediction_becomes_agent_opinion():

    prediction = PredictionResult(
        model_id=uuid4(),
        model_version="xgboost-v1",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        confidence=0.72,
        raw_output={
            "probability_long": 0.72,
            "probability_short": 0.18,
        },
        explainability={
            "top_features": [
                "RSI",
                "ATR",
            ]
        },
        timestamp=datetime.now(),
    )

    adapter = MLAgentAdapter()

    opinion = adapter.to_opinion(prediction)

    assert opinion.domain == AgentDomain.QUANT
    assert opinion.direction == "LONG"
    assert opinion.confidence == 0.72
    assert len(opinion.evidence) > 0
    assert opinion.effective_influence > 0
