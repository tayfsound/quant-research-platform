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


def select_threshold(
    samples: list[tuple[float, float]], min_sample: int = MIN_SAMPLE_SIZE
) -> dict | None:
    """Faz 482 — grid-search'ün SAF hâli: (confidence, pnl) çiftlerinden
    en yüksek ORTALAMA kâr (expectancy) veren act_threshold'u seçer.
    "Eğer sadece confidence >= t olan işlemleri alsaydım işlem başına
    ortalama kârım ne olurdu" sorusunu her aday eşik için hesaplar.

    I/O'dan AYRILDI çünkü DB'ye gömülü hâli paylaşılan quantdb_test'te
    deterministik test edilemiyordu: sonuç, o an tabloda ne olduğuna
    bağlıydı (bu yüzden aynı test izole geçip tam pakette düşüyordu).
    `compute_suggested_thresholds()` bu fonksiyonu gerçek satırlarla
    besleyen ince bir sarmalayıcı — davranış birebir aynı."""
    if len(samples) < min_sample:
        return None

    best_act = None
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

    if best_reward is None or best_act is None:
        return None

    # Faz 482 (2026-09-10) — İKİNCİ canlı kilitlenme olayı, gerçek veriyle
    # ölçüldü. Faz 370'in SUM->MEAN düzeltmesi ızgarayı "en yüksek eşiğe"
    # doğru sistematik kaymaktan kurtardı ama asıl tuzağı kapatmadı: ızgara
    # NOKTALARININ HEPSİ negatif expectancy verdiğinde bu fonksiyon yine de
    # "en az kötü" olanı seçip CANLIYA yazıyordu. Gerçek ölçüm (9 Eylül, son
    # 500 kapanmış işlem): t=0,40 -> -0,60 $/işlem, t=0,50 -> -0,93,
    # t=0,65 -> -0,96, t=0,70 -> -1,02, t=0,80 -> -3,66. Hepsi negatif;
    # aralarındaki fark gürültü. Sonuç: act_threshold saatlik turlarda
    # 0,40 ile 0,70 arasında gidip geliyordu ve 0,70'e sıçradığı her turda
    # sistem fiilen duruyordu (açılma oranı %30,7 -> %1,2; canlı doğrulama:
    # kararların içine yazılmış act_threshold değeri 9 Eylül'de 2784 kez
    # 0,70, 116 kez 0,65, 67 kez 0,40).
    #
    # Kural: pozitif expectancy YOKSA hiçbir şey yazılmaz. "Hiçbir eşik bu
    # işlemleri kârlı yapmıyor" bulgusu, bir eşik seçme gerekçesi DEĞİL —
    # problem eşikte değil, işlemlerin kendisinde. Bu, modülün zaten
    # benimsediği "yeterli veri yoksa dürüstçe None dön, icat edilmiş bir
    # sayı yazma" ilkesinin aynısı, sadece örneklem sayısına değil kanıtın
    # İŞARETİNE uygulanmış hâli.
    #
    # BİLİNEN, BU VERİYLE ÇÖZÜLEMEYEN KISIT (kasıtlı olarak düzeltilmedi):
    # örneklem survivorship-biased — list_closed_trades SADECE açılmış
    # pozisyonları içerir, onlar da o günkü act_threshold'u geçtikleri için
    # oradadır. Yani fonksiyon, kendi kestiği bir dağılım üzerinde kendini
    # kalibre ediyor. Düşük-confidence işlemlerin pnl'i hiç gözlenmediği
    # için bu, daha akıllı bir formülle DEĞİL sadece daha geniş bir
    # örneklemle çözülebilir — Faz 482'nin kapı carve-out'u (bkz. services/
    # decision_recorder.py::_routes_to_real_exchange) simüle sembollerde
    # confidence aralığının tamamını açtığı için önümüzdeki günlerde
    # örneklem doğal olarak temsili hâle gelecek.
    if best_reward <= 0:
        return None

    reduce_threshold = round(max(0.25, best_act - 0.3), 3)

    return {
        "act_threshold": best_act,
        "reduce_threshold": reduce_threshold,
        "sample_size": best_sample_size,
        "best_reward": round(best_reward, 4),
    }


def compute_suggested_thresholds(min_sample: int = MIN_SAMPLE_SIZE) -> dict | None:
    """`select_threshold()`'u GERÇEK, kalıcı `decisions` tablosundaki son
    500 kapanmış işlemle besleyen ince sarmalayıcı. Yeterli örnek yoksa ya
    da hiçbir aday eşik pozitif expectancy vermiyorsa None döner — icat
    edilmiş bir sayı canlı ayara asla yazılmaz."""
    with SessionFactory.get_session() as session:
        trades = DecisionPersistor(session).list_closed_trades(limit=500)

    samples = [
        (t["confidence"], t["pnl"])
        for t in trades
        if t.get("confidence") is not None and t.get("pnl") is not None
    ]
    return select_threshold(samples, min_sample=min_sample)
