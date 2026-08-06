"""Faz 204: MetaStage'in act_threshold/reduce_threshold değerlerinin
GERÇEK kapalı işlem geçmişinden kendi kendini kalibre etmesi.

Mevcut services/meta_learner.py aynı fikri (reward-tabanlı grid search)
doğru uyguluyordu ama iki yerden kırıktı: (1) her Celery task çalışmasında
yeni bir CognitiveOrchestrator/LearningLoop/MetaLearner nesnesi kuruluyordu,
bu yüzden in-memory history hiçbir zaman gereken pencereye ulaşamıyordu;
(2) hesaplanan öneri hiçbir zaman gerçek eşiğe geri yazılmıyordu — sadece
bir stats sözlüğünde duruyordu. Bu modül aynı fikri GERÇEK, kalıcı
`decisions` tablosundaki kapanmış işlemlerden besliyor ve sonucu
app_settings'e yazarak MetaStage'in gerçekten okuduğu değeri değiştiriyor."""
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory

MIN_SAMPLE_SIZE = 20
ACT_CANDIDATES = [t / 100 for t in range(40, 91, 5)]  # 0.40, 0.45, ..., 0.90


def compute_suggested_thresholds(min_sample: int = MIN_SAMPLE_SIZE) -> dict | None:
    """Gerçek kapanmış işlemlerin (confidence, pnl) çiftlerinden, geriye
    dönük olarak en yüksek toplam kâr üretecek act_threshold'u grid-search
    ile bulur — "eğer sadece confidence >= t olan işlemleri alsaydım toplam
    kârım ne olurdu" sorusunu her aday eşik için gerçekten hesaplıyor.
    Yeterli örnek yoksa None döner (icat edilmiş bir sayı değil, dürüstçe
    'henüz yeterli veri yok')."""
    with SessionFactory.get_session() as session:
        trades = DecisionPersistor(session).list_closed_trades(limit=500)

    samples = [
        (t["confidence"], t["pnl"])
        for t in trades
        if t.get("confidence") is not None and t.get("pnl") is not None
    ]
    if len(samples) < min_sample:
        return None

    best_act = 0.7
    best_reward = None
    for t in ACT_CANDIDATES:
        total_reward = sum(pnl for conf, pnl in samples if conf >= t)
        if best_reward is None or total_reward > best_reward:
            best_reward = total_reward
            best_act = t

    reduce_threshold = round(max(0.25, best_act - 0.3), 3)

    return {
        "act_threshold": best_act,
        "reduce_threshold": reduce_threshold,
        "sample_size": len(samples),
        "best_reward": round(best_reward, 4),
    }
