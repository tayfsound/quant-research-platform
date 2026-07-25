"""Model değerlendirme metrikleri."""
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score


def evaluate_classification(model, x, y) -> dict:
    preds = model.predict(X)
    return {
        "accuracy": accuracy_score(y, preds),
        "precision": precision_score(y, preds, average="weighted", zero_division=0),
        "recall": recall_score(y, preds, average="weighted", zero_division=0),
        "f1": f1_score(y, preds, average="weighted", zero_division=0),
    }
