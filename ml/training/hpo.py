"""Hiperparametre optimizasyonu."""
import optuna


def optimize_xgboost(x, y, n_trials: int = 10) -> dict:
    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3),
        }
        from sklearn.model_selection import cross_val_score
        from xgboost import XGBClassifier
        model = XGBClassifier(**params)
        scores = cross_val_score(model, x, y, cv=3)
        return scores.mean()

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials)
    return study.best_params
