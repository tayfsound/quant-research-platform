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

# Faz 370-devam — KRİTİK canlı olay: eski sürüm `total_reward = sum(pnl for
# conf, pnl in samples if conf >= t)` kullanıyordu — TOPLAM, ortalama değil.
# Genel performans negatifken (bu turda doğrulandı: son 500 kapanmış işlem
# Sharpe=-0.046) bu ödül SUM'u eşik yükseldikçe (daha az işlem dahil olunca)
# yapısal olarak "daha az negatif"e, sınırda (t=0.90, örneklem neredeyse
# boşalınca) 0'a yaklaşıyordu — 0 her negatif toplamdan büyük olduğu için
# grid-search HER ZAMAN en yüksek adayı (0.90) seçmeye zorlanıyordu. Bu
# "en iyi eşiği bulma" değil "en az işlemi dahil ederek toplam zararı en
# aza indirme" oluyordu — kendi kendini besleyen bir kilitlenmeydi (eşik
# yükselince yeni işlem açılmıyor, sonraki task çalışmasında da aynı eski/
# kötü 500 işlem görülüp aynı sonuca varılıyordu). Canlıda gerçekten
# act_threshold=0.9/reduce_threshold=0.6'ya kilitlenip sistemi durdurdu.
#
# Düzeltme: (1) SUM yerine MEAN (expectancy) — bir adayın skoru, o eşiği
# geçen işlemlerin ORTALAMA pnl'i, sadece kaç tanesinin toplamı değil, bu
# yüzden örneklemi daraltmak artık otomatik olarak skoru iyileştirmiyor.
# (2) Her adayın kendi alt-örneklemi de MIN_SAMPLE_SIZE'ı geçmeli — aksi
# halde 2-3 şanslı işlemin ortalaması gürültüyle en yüksek eşiği kazanabilir.
# Hiçbir aday yeterli örnekliğe ulaşamazsa (mevcut confidence dağılımı çok
# düşükse) fonksiyon dürüstçe None döner — icat edilmiş bir eşik yazılmaz.
MIN_CANDIDATE_SAMPLE_SIZE = MIN_SAMPLE_SIZE


def compute_suggested_thresholds(min_sample: int = MIN_SAMPLE_SIZE) -> dict | None:
    """Gerçek kapanmış işlemlerin (confidence, pnl) çiftlerinden, geriye
    dönük olarak en yüksek ORTALAMA kâr (expectancy) üretecek act_threshold'u
    grid-search ile bulur — "eğer sadece confidence >= t olan işlemleri
    alsaydım işlem başına ortalama kârım ne olurdu" sorusunu her aday eşik
    için gerçekten hesaplıyor. Yeterli örnek yoksa (genel ya da adayın kendi
    alt-örneklemi) None döner (icat edilmiş bir sayı değil, dürüstçe
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
    best_sample_size = 0
    for t in ACT_CANDIDATES:
        subset = [pnl for conf, pnl in samples if conf >= t]
        if len(subset) < MIN_CANDIDATE_SAMPLE_SIZE:
            continue
        mean_reward = sum(subset) / len(subset)
        if best_reward is None or mean_reward > best_reward:
            best_reward = mean_reward
            best_act = t
            best_sample_size = len(subset)

    if best_reward is None:
        return None

    reduce_threshold = round(max(0.25, best_act - 0.3), 3)

    return {
        "act_threshold": best_act,
        "reduce_threshold": reduce_threshold,
        "sample_size": best_sample_size,
        "best_reward": round(best_reward, 4),
    }
