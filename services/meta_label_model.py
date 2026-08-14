"""Faz 268-sonrası — kullanıcı isteği: gerçek meta-labeling (Marcos López
de Prado'nun terimiyle) — "LONG sinyali güzel ama bu koşullarda LONG
açmaya değmez mi" sorusunu, council'in kendi yön tahmininden AYRI olarak
öğrenen ikinci bir model. Birincil model (9 ajan council'i) hâlâ yönü
belirliyor — bu DEĞİŞMİYOR. Bu modül SADECE, o yönlü sinyal verildiğinde
gerçekte TP'nin mi SL'nin mi önce geleceğini (P(TP before SL)) gerçek
kapanmış işlemlerden öğreniyor.

Kasıtlı olarak services/agent_confidence_model.py ile AYNI mimari
(lojistik regresyon, gerçek train/test split, gerçek accuracy/AUC,
yetersiz veride fail-closed None) — aynı kullanıcı tarafından zaten
onaylanmış, üretimde çalışan bir desen tekrarlanıyor, icat edilmiş yeni
bir yaklaşım değil.

KRİTİK — "yeni karmaşıklık kendi edge'ini kanıtlamalı" ilkesi: bu model
HİÇBİR canlı karara BAĞLANMIYOR. train_meta_label_model() gerçek OOS
(train/test) doğrulama metriklerini (test_accuracy, test_auc,
baseline_correctness_rate) döndürür — sadece bunlar gerçekten taban
oranını yeniyorsa (ve kullanıcı ayrıca onaylarsa) DecisionFusion'a
bağlanması bir sonraki, ayrı bir adımdır (bkz. Adaptive Barrier Engine
ile AYNI, zaten kurulmuş emsal — orası da OOS'u geçti ama backtest/canlı
uçurumu netleşmeden bilerek bağlanmadı)."""
from sqlalchemy import text

from contracts.agent_confidence_model import AgentConfidenceModel
from services.agent_confidence_model import ConfidenceModelRepository, _normalize_raw_features, _vectorize

DEFAULT_WINDOW = 1000
MIN_TRAINING_SAMPLES = 100
META_LABEL_DOMAIN = "meta_label"

# Gerçek market_snapshot.features'ta bulunan, karar ANINDA elde olan
# (lookahead yok) alanlar + planned_rr_ratio/confidence (aşağıda ayrıca
# hesaplanıp enjekte ediliyor — decisions tablosunun kendi kolonlarından
# gelir, features dict'inde değildir).
META_LABEL_FEATURE_SCHEMA = {
    "numeric": [
        "confidence", "planned_rr_ratio", "adx", "di_plus", "di_minus",
        "rsi_value", "hurst_exponent", "realized_vol_percentile",
        "bollinger_percent_b", "vwap_deviation_pct",
    ],
    "boolean": ["volume_confirmation"],
    "categorical": ["trend", "momentum", "market_structure", "volatility_regime", "long_term_trend_regime"],
}


def _extract_meta_label_training_rows(window: int) -> tuple[list[dict], list[int]]:
    """Gerçek kapanmış işlemlerden (SADECE exit_reason take_profit/
    stop_loss — TP-önce-mi-SL-önce-mi yarışının kendisi bu ikisiyle
    tanımlı, manual_*/breakeven_stop/time_expired bu yarışı temsil
    etmiyor, dışarıda bırakılıyor) özellik + etiket (1=TP, 0=SL) çıkarır."""
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                "SELECT agent_contributions, entry_price, stop_loss_price, "
                "take_profit_price, confidence, outcome "
                "FROM decisions "
                "WHERE status = 'closed' AND excluded_from_stats = false "
                "AND outcome ->> 'exit_reason' IN ('take_profit', 'stop_loss') "
                "ORDER BY closed_at DESC LIMIT :limit"
            ),
            {"limit": window},
        ).mappings().all()

    feats_list = []
    labels = []
    for row in rows:
        entry_price = row["entry_price"]
        stop_loss_price = row["stop_loss_price"]
        take_profit_price = row["take_profit_price"]
        if not entry_price or not stop_loss_price or not take_profit_price:
            continue

        raw_features = None
        for contribution in row["agent_contributions"]:
            if isinstance(contribution, dict) and contribution.get("type") == "market_snapshot":
                raw_features = (contribution.get("data") or {}).get("features", {})
                break
        if raw_features is None:
            continue

        planned_stop_pct = abs(entry_price - stop_loss_price) / entry_price
        planned_target_pct = abs(take_profit_price - entry_price) / entry_price
        if planned_stop_pct <= 0:
            continue

        feats = _normalize_raw_features(raw_features)
        feats["planned_rr_ratio"] = planned_target_pct / planned_stop_pct
        feats["confidence"] = row["confidence"] or 0.0

        feats_list.append(feats)
        labels.append(1 if row["outcome"].get("exit_reason") == "take_profit" else 0)

    return feats_list, labels


def train_meta_label_model(
    window: int = DEFAULT_WINDOW,
    min_samples: int = MIN_TRAINING_SAMPLES,
) -> AgentConfidenceModel | None:
    """Fail-closed: yeterli örneklem yoksa ya da etiketler tek sınıfsa
    (hep TP ya da hep SL) None döner — gürültüden bir model üretilmez.
    Dönen modelin test_accuracy/test_auc/baseline_correctness_rate
    alanları GERÇEK OOS doğrulamadır — bu modeli canlıya bağlamadan önce
    bunların taban oranını gerçekten yenip yenmediği elle
    değerlendirilmeli."""
    import numpy as np

    feats_list, labels = _extract_meta_label_training_rows(window)
    if len(feats_list) < min_samples:
        return None

    schema = META_LABEL_FEATURE_SCHEMA
    categorical_values = {
        key: sorted(set((f.get(key) or "unknown") for f in feats_list))
        for key in schema["categorical"]
    }

    X = _vectorize(feats_list, schema, categorical_values)
    y = np.array(labels)
    if len(set(y.tolist())) < 2:
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
        domain=META_LABEL_DOMAIN,
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


def predict_tp_probability(
    features: dict,
    repository: ConfidenceModelRepository | None = None,
) -> float | None:
    """P(TP before SL) tahmini — henüz eğitilmiş/kaydedilmiş bir model
    yoksa None (fail-closed, asla uydurulmuş bir olasılık döndürülmez).
    Kasıtlı olarak hiçbir canlı karar yolundan ÇAĞRILMIYOR — sadece
    araştırma/doğrulama amaçlı."""
    import numpy as np

    repo = repository or ConfidenceModelRepository()
    model = repo.get_latest(META_LABEL_DOMAIN)
    if model is None or not model.coefficients:
        return None

    feats = _normalize_raw_features(features)
    categorical_values = model.categorical_features
    schema = {
        "numeric": model.numeric_features,
        "boolean": model.boolean_features,
        "categorical": list(categorical_values.keys()),
    }
    X = _vectorize([feats], schema, categorical_values)
    X_scaled = (X - np.array(model.scaler_mean)) / np.array(model.scaler_scale)
    z = float(np.dot(X_scaled[0], model.coefficients) + model.intercept)
    probability = 1.0 / (1.0 + np.exp(-z))
    return round(float(probability), 4)
