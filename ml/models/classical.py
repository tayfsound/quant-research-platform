"""Klasik ML modelleri."""
import lightgbm as lgb
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier


class ClassicalModels:
    @staticmethod
    def train_xgboost(x, y):
        model = xgb.XGBClassifier(n_estimators=100, max_depth=5, n_jobs=1, tree_method="hist")
        model.fit(x, y)
        return model

    @staticmethod
    def train_lightgbm(x, y):
        model = lgb.LGBMClassifier(n_estimators=100)
        model.fit(x, y)
        return model

    @staticmethod
    def train_random_forest(x, y):
        model = RandomForestClassifier(n_estimators=100)
        model.fit(x, y)
        return model

    @staticmethod
    def train_catboost(x, y):
        from catboost import CatBoostClassifier
        model = CatBoostClassifier(iterations=100, verbose=0)
        model.fit(x, y)
        return model
