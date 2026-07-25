"""ML modülü testleri."""
import numpy as np

from ml.models.classical import ClassicalModels


def test_xgboost_train():
    X = np.random.rand(100, 10)
    y = np.random.randint(0, 3, 100)
    model = ClassicalModels.train_xgboost(X, y)
    assert model is not None
    preds = model.predict(X[:5])
    assert len(preds) == 5
