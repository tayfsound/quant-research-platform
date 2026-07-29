"""Model Evaluator — Modellerin performansını finansal ve istatistiksel olarak ölçer."""
import numpy as np
from typing import Any, List
from pydantic import BaseModel

class EvaluationResult(BaseModel):
    # İstatistiksel Metrikler
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    
    # Finansal Metrikler
    total_pnl: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    
    # Bilişsel Metrikler
    avg_confidence: float = 0.0
    calibration_error: float = 0.0

class ModelEvaluator:
    def __init__(self):
        pass

    def evaluate_predictions(self, predictions: List[dict]) -> EvaluationResult:
        """Tahmin listesini değerlendirir.
        predictions: [{'pred': int, 'actual': int, 'pnl': float, 'confidence': float}]
        """
        if not predictions:
            return EvaluationResult()

        preds = np.array([p['pred'] for p in predictions])
        actuals = np.array([p['actual'] for p in predictions])
        pnls = np.array([p['pnl'] for p in predictions])
        confidences = np.array([p['confidence'] for p in predictions])

        # İstatistiksel hesaplamalar
        tp = np.sum((preds == 1) & (actuals == 1))
        fp = np.sum((preds == 1) & (actuals == 0))
        fn = np.sum((preds == 0) & (actuals == 1))
        tn = np.sum((preds == 0) & (actuals == 0))

        total = len(predictions)
        accuracy = (tp + tn) / total
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        # Finansal hesaplamalar
        total_pnl = np.sum(pnls)
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        win_rate = len(wins) / len(pnls) if len(pnls) > 0 else 0.0
        
        profit_factor = abs(np.sum(wins) / np.sum(losses)) if len(losses) > 0 else (999.0 if np.sum(wins) > 0 else 0.0)
        
        # Sharpe Ratio
        std_pnl = np.std(pnls)
        sharpe = np.mean(pnls) / std_pnl * np.sqrt(252) if std_pnl > 0 else 0.0
        
        # Max Drawdown
        cum_pnl = np.cumsum(pnls)
        peak = np.maximum.accumulate(cum_pnl)
        drawdown = peak - cum_pnl
        max_dd = np.max(drawdown) if len(drawdown) > 0 else 0.0

        # Bilişsel metrikler
        avg_conf = np.mean(confidences)
        calibration_error = np.mean(np.abs(confidences - actuals))

        return EvaluationResult(
            accuracy=round(float(accuracy), 4),
            precision=round(float(precision), 4),
            recall=round(float(recall), 4),
            f1_score=round(float(f1), 4),
            total_pnl=round(float(total_pnl), 4),
            sharpe_ratio=round(float(sharpe), 4),
            max_drawdown=round(float(max_dd), 4),
            win_rate=round(float(win_rate), 4),
            profit_factor=round(float(profit_factor), 4),
            avg_confidence=round(float(avg_conf), 4),
            calibration_error=round(float(calibration_error), 4)
        )
