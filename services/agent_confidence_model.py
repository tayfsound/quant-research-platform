"""Faz 264: kayan pencereli, periyodik yeniden eğitilen ajan-içi güven
kalibrasyonu. technical_agent.py'nin kendi skor formülü (+1.0 trend,
-1.0 RSI aşırılık, vb.) DEĞİŞMİYOR — bu modül sadece o formülün ürettiği
confidence'ı, aynı özelliklerin GERÇEKTE ne kadar doğru çıktığına göre
ayarlıyor. Model hiç eğitilmemişse ya da yetersiz veri varsa çarpan 1.0
(no-op) — fail-closed, asla icat edilmiş bir ayar uygulanmaz.

Kullanıcı kararı (Faz 264 tartışması): "piyasa sabit değil, sürekli bir
devinim içinde" — bu yüzden model TEK SEFERLİK değil, düzenli aralıklarla
(bkz. services/tasks.py::retrain_agent_confidence_models_task) SADECE SON
`window` gerçek kapanmış işlem üzerinden yeniden eğitiliyor; piyasa rejimi
değiştikçe model de haftalar içinde bunu yansıtıyor."""
import os
from pathlib import Path

import numpy as np
from sqlalchemy import text

from contracts.agent_confidence_model import AgentConfidenceModel

# Faz 264: AgentMemory ile aynı desen (bkz. services/agent_memory.py) —
# testler gerçek confidence_model_history/ dizinini kirletmesin/ondan
# etkilenmesin diye conftest.py bunu izole bir test dizinine yönlendiriyor.
_DEFAULT_STORAGE_PATH = os.environ.get("AGENT_CONFIDENCE_MODEL_STORAGE_PATH", "confidence_model_history")

DEFAULT_WINDOW = 500
MIN_TRAINING_SAMPLES = 100
# Faz 264: çarpan aşırı uçlara savrulmasın diye sınırlı — model gürültülü
# bir tahmin yapsa bile tek bir cycle'ın kararını gülünç bir şekilde
# şişirmesin/söndürmesin.
MULTIPLIER_MIN = 0.5
# Faz 362-devam — kullanıcı kararı (2026-08-24): önceki üst sınır (1.5)
# "pozisyon boyutu çarpanları SADECE küçültür, asla büyütmez" ilkesine
# (docs/index.md) TEORİK bir gedik açıyordu — bu, TEK bir ajanın
# confidence'ını yukarı çekebiliyordu, bu da dolaylı yoldan genel karar
# confidence'ını (dolayısıyla Kelly boyutlandırmayı) büyütebilirdi. Artık
# diğer TÜM çarpanlarla (kelly_size_multiplier, meta_label_size_
# multiplier, InnerCritic, pyramid_dampened_leverage vb.) AYNI ilke:
# SADECE küçültebilir, asla büyütemez — "bu ajan tahmin ettiğinden daha
# az doğru çıkmış" sinyali hâlâ confidence'ı düşürür, ama "daha çok doğru
# çıkmış" sinyali artık YUKARI çekmiyor (mevcut 1.0'da kalıyor).
MULTIPLIER_MAX = 1.0

# technical_agent.py'nin kendi TechnicalContext'inde GERÇEKTEN elinde olan
# alanlarla birebir aynı — model, ajanın kendisinin göremediği bir
# özelliği "öğrenmiş" gibi davranmasın diye kasıtlı olarak bu sınıra
# çekildi (bkz. contracts/technical.py).
FEATURE_SCHEMAS: dict[str, dict[str, list[str]]] = {
    "technical": {
        "numeric": ["rsi_value", "adx", "di_plus", "di_minus", "bollinger_percent_b",
                    "bollinger_bandwidth", "vwap_deviation_pct"],
        "boolean": ["volume_confirmation"],
        "categorical": ["trend", "momentum", "market_structure", "ema_alignment", "volatility_regime"],
    },
}

# market_snapshot.features içindeki ham anahtar adları, ajanların kendi
# Context sınıflarının alan adlarından farklı olabiliyor (ör. "RSI" vs
# TechnicalContext.rsi_value). Eğitim verisi decisions.agent_contributions'
# taki HAM feature dict'inden çekiliyor, çıkarım ise (council_orchestrator
# içinde) doğrudan TechnicalContext'ten — ikisi de bu haritalamadan geçip
# AYNI kanonik (Context alan) adlarına normalize ediliyor, _vectorize()
# tek bir isim seti görüyor.
_RAW_TO_CANONICAL_FEATURE_KEYS = {"RSI": "rsi_value"}


def _normalize_raw_features(feats: dict) -> dict:
    normalized = dict(feats)
    for raw_key, canonical_key in _RAW_TO_CANONICAL_FEATURE_KEYS.items():
        if raw_key in normalized and canonical_key not in normalized:
            normalized[canonical_key] = normalized.pop(raw_key)
    return normalized


class ConfidenceModelRepository:
    """WeightRepository ile aynı desen (dosya tabanlı, domain başına en
    son model) — Class 2 audit verisi değil, öğrenilmiş bir artefakt."""

    def __init__(self, storage_path: str = _DEFAULT_STORAGE_PATH):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def save(self, model: AgentConfidenceModel) -> AgentConfidenceModel:
        filename = self.storage_path / f"{model.domain}_latest.json"
        filename.write_text(model.model_dump_json(indent=2))
        return model

    def get_latest(self, domain: str) -> AgentConfidenceModel | None:
        filename = self.storage_path / f"{domain}_latest.json"
        if not filename.exists():
            return None
        return AgentConfidenceModel.model_validate_json(filename.read_text())


def _extract_training_rows(domain: str, window: int) -> tuple[list[dict], list[int]]:
    """Gerçek kapanmış işlemlerden (agent_contributions içindeki gerçek
    market_snapshot özellikleri + gerçek pnl) bu domain'in kendi yönlü
    oylarını ve gerçekte doğru çıkıp çıkmadığını (was_correct) çıkarır."""
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        rows = session.execute(text("""
            SELECT direction, pnl, agent_contributions, closed_at
            FROM decisions
            WHERE status='closed' AND excluded_from_stats=false AND closed_at IS NOT NULL
            ORDER BY closed_at DESC
            LIMIT :limit
        """), {"limit": window}).mappings().all()

    feats_list = []
    labels = []
    for r in rows:
        executed_direction = (r["direction"] or "").upper()
        pnl = r["pnl"]
        if pnl is None or executed_direction not in ("LONG", "SHORT"):
            continue
        profitable = pnl > 0
        feats = None
        agent_direction = None
        for c in r["agent_contributions"]:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "market_snapshot":
                feats = (c.get("data") or {}).get("features", {})
            if c.get("domain") == domain:
                agent_direction = (c.get("direction") or "").upper()
        if feats is None or agent_direction not in ("LONG", "SHORT"):
            continue
        was_correct = profitable if agent_direction == executed_direction else not profitable
        feats_list.append(_normalize_raw_features(feats))
        labels.append(int(was_correct))

    return feats_list, labels


def _vectorize(
    feats_list: list[dict],
    schema: dict[str, list[str]],
    categorical_values: dict[str, list[str]],
) -> np.ndarray:
    numeric = schema["numeric"]
    boolean = schema["boolean"]
    categorical = schema["categorical"]

    rows = []
    for feats in feats_list:
        row = []
        for key in numeric:
            v = feats.get(key)
            row.append(float(v) if v is not None else 0.0)
        for key in boolean:
            row.append(1.0 if feats.get(key) else 0.0)
        for key in categorical:
            val = feats.get(key) or "unknown"
            for cat_val in categorical_values[key]:
                row.append(1.0 if val == cat_val else 0.0)
        rows.append(row)
    return np.array(rows) if rows else np.zeros((0, len(numeric) + len(boolean) + sum(len(v) for v in categorical_values.values())))


def train_confidence_model(
    domain: str,
    window: int = DEFAULT_WINDOW,
    min_samples: int = MIN_TRAINING_SAMPLES,
) -> AgentConfidenceModel | None:
    """Fail-closed: yeterli örneklem yoksa (min_samples) None döner —
    caller eski modeli (varsa) korumalı, asla gürültüden bir model
    üretilmemeli."""
    schema = FEATURE_SCHEMAS.get(domain)
    if schema is None:
        return None

    feats_list, labels = _extract_training_rows(domain, window)
    if len(feats_list) < min_samples:
        return None

    categorical_values = {
        key: sorted(set((f.get(key) or "unknown") for f in feats_list))
        for key in schema["categorical"]
    }

    X = _vectorize(feats_list, schema, categorical_values)
    y = np.array(labels)

    if len(set(y.tolist())) < 2:
        # Tek sınıf (hep doğru ya da hep yanlış) — lojistik regresyon
        # tanımsız, anlamlı bir model yok.
        return None

    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, roc_auc_score
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y if min(np.bincount(y)) >= 2 else None,
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    model = LogisticRegression(max_iter=2000, C=1.0)
    model.fit(X_train_s, y_train)

    train_acc = accuracy_score(y_train, model.predict(X_train_s))
    test_acc = accuracy_score(y_test, model.predict(X_test_s))
    try:
        test_auc = roc_auc_score(y_test, model.predict_proba(X_test_s)[:, 1])
    except ValueError:
        test_auc = None

    return AgentConfidenceModel(
        domain=domain,
        window_size=window,
        sample_count=len(feats_list),
        numeric_features=schema["numeric"],
        boolean_features=schema["boolean"],
        categorical_features=categorical_values,
        scaler_mean=scaler.mean_.tolist(),
        scaler_scale=scaler.scale_.tolist(),
        coefficients=model.coef_[0].tolist(),
        intercept=float(model.intercept_[0]),
        baseline_correctness_rate=float(y.mean()),
        train_accuracy=float(train_acc),
        test_accuracy=float(test_acc),
        test_auc=float(test_auc) if test_auc is not None else None,
    )


def predict_confidence_multiplier(
    domain: str,
    features: dict,
    repository: ConfidenceModelRepository | None = None,
) -> float:
    """Henüz eğitilmiş bir model yoksa 1.0 (no-op) — fail-closed."""
    repo = repository or ConfidenceModelRepository()
    model = repo.get_latest(domain)
    if model is None or not model.coefficients:
        return 1.0

    schema = {
        "numeric": model.numeric_features,
        "boolean": model.boolean_features,
        "categorical": list(model.categorical_features.keys()),
    }
    X = _vectorize([features], schema, model.categorical_features)
    mean = np.array(model.scaler_mean)
    scale = np.array(model.scaler_scale)
    scale_safe = np.where(scale == 0, 1.0, scale)
    X_scaled = (X - mean) / scale_safe

    z = float(np.dot(X_scaled[0], model.coefficients) + model.intercept)
    p_correct = 1.0 / (1.0 + np.exp(-z))

    baseline = model.baseline_correctness_rate or 0.5
    multiplier = p_correct / baseline if baseline > 0 else 1.0
    return float(np.clip(multiplier, MULTIPLIER_MIN, MULTIPLIER_MAX))
