"""Model Evaluation testleri."""
import pytest

from ml.registry.store import ModelRegistry
from ml.training.evaluation import ModelEvaluator
from ml.training.pipeline import TrainingPipeline


def test_model_evaluator_metrics():
    evaluator = ModelEvaluator()

    # Test verisi: 4 tahmin, 3 doğru, 1 yanlış. Toplam PnL: 100
    predictions = [
        {'pred': 1, 'actual': 1, 'pnl': 50.0, 'confidence': 0.9},
        {'pred': 1, 'actual': 1, 'pnl': 70.0, 'confidence': 0.8},
        {'pred': 0, 'actual': 0, 'pnl': 0.0, 'confidence': 0.7},
        {'pred': 1, 'actual': 0, 'pnl': -20.0, 'confidence': 0.6},
    ]

    result = evaluator.evaluate_predictions(predictions)

    assert result.accuracy == 0.75
    assert result.precision == pytest.approx(0.6667, abs=1e-4)
    assert result.total_pnl == 100.0
    assert result.win_rate == 0.5 # 2 win, 2 non-win (1 loss, 1 zero)
    assert result.avg_confidence == 0.75

def test_training_pipeline_with_evaluation():
    registry = ModelRegistry()
    pipeline = TrainingPipeline(registry)

    predictions = [
        {'pred': 1, 'actual': 1, 'pnl': 10.0, 'confidence': 0.8},
        {'pred': 0, 'actual': 1, 'pnl': -5.0, 'confidence': 0.4},
    ]

    entry = pipeline.run(
        model_type="xgboost_trend",
        predictions=predictions,
        hyperparams={"n_estimators": 100}
    )

    assert entry.model_type == "xgboost_trend"
    assert "accuracy" in entry.metrics
    assert entry.metrics["total_pnl"] == 5.0
    assert entry.hyperparameters["n_estimators"] == 100
