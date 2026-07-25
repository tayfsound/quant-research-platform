"""XGBoost ile ilk model eğitimi (sahte etiketlerle demo)."""
import numpy as np

from ml.checkpoint import CheckpointManager
from ml.models.classical import ClassicalModels


def main():
    # Demo veri
    X = np.random.rand(500, 5)  # 5 feature
    y = np.random.randint(0, 3, 500)  # 3 sınıf: short, neutral, long

    model = ClassicalModels.train_xgboost(X, y)
    ckpt = CheckpointManager("checkpoints")
    ckpt.save(model, "xgboost_demo_v1")
    print("✅ Model eğitildi ve kaydedildi.")

if __name__ == "__main__":
    main()
