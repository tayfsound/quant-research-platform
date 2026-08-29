"""Faz 268g — "İsabeti artırmanın yolu daha akıllı kullanım" yol
haritasının D fazı (Signal-Strength Position Sizing).

Gerçek bulgu: engines/cognitive_pipeline.py::MetaStage zaten 3 kademeli
boyutlandırma yapıyor — WAIT (confidence < reduce_threshold) -> 0,
REDUCE (reduce_threshold <= confidence < act_threshold) -> proposed_size
* confidence (zaten confidence'a orantılı), ACT (confidence >= act_
threshold) -> proposed_size'ın TAMAMI, hiç ek ölçeklendirme yok. Yani
confidence=0.71 ile confidence=0.99 AYNI büyüklükte açılıyor — raporun
"confidence 0.85 ile 0.40 aynı büyüklükte açılıyor" iddiası abartılıydı
(0.40 REDUCE'da zaten küçülüyor), ama ACT-tier içindeki bu fark gerçek.

Çözüm: ACT-tier'de, o confidence kovasının GERÇEK geçmiş kazanç/kayıp
dağılımından (decisions.confidence + pnl — confidence_calibration.py'nin
zaten kullandığı AYNI veri kaynağı) half-Kelly formülüyle bir çarpan
hesaplanır. Yeterli veri yoksa (fail-closed) çarpan 1.0 — mevcut davranış
(tam boyut) korunur, icat edilmiş bir küçültme uygulanmaz. Çarpan HER
ZAMAN [0,1] aralığında — AI kendi risk tavanını (mevcut tam boyut)
büyütemez, sadece küçültebilir."""
import time
from collections import defaultdict

# Faz 363 — kullanıcı isteği: gerçek veriyle ölçüldü (3.302 kapanmış işlem,
# 10 confidence kovası + 46 rejim×confidence kovası) — 20'den 50'ye
# çıkarmak confidence-only kovada kapsamayı neredeyse hiç düşürmüyor
# (%99.5→%99.5, sadece zaten istatistiksel olarak anlamsız uç kovalar
# etkisiz kalıyor), rejim×confidence kovada %96.0→%85.8 (18/46 kova
# hayatta, hâlâ sağlam bir denge). 100+'a çıkarmak rejim kovasının
# ÇOĞUNU (100'de sadece 13/46) öldürüyordu — kademeli olarak (veri
# arttıkça) 100/150/200'e çıkılacak, bkz. AI_MEMORY_SYSTEM/BACKLOG.md.
_MIN_BUCKET_SAMPLES = 50
_CACHE_TTL_SECONDS = 300
_HALF_KELLY_FACTOR = 0.5
_cache: dict = {"stats": None, "computed_at": 0.0}
_regime_cache: dict = {"stats": None, "computed_at": 0.0}

# Faz 370-devam — KRİTİK canlı olay (2026-08-29, kullanıcı bulgusu):
# çarpan literal 0.0'a inebiliyordu — bu modülün DIŞINDAKİ TÜM diğer
# boyutlandırma kapıları (self_correction/self_model/pivotal_agent/
# symbol_performance/mae_mfe_bucket) "asla sıfıra inme, sadece küçült"
# ilkesiyle bir MIN_MULTIPLIER tabanı kullanıyordu — kelly_size_
# multiplier bu tutarlılığın DIŞINDA kalmıştı. Gerçek sonuç: son 500
# kapanmış işlemin negatif Sharpe'ı (-0.046) bazı confidence kovalarını
# 0.0'a düşürünce sistem HİÇ yeni işlem açamadı — ve yeni işlem
# açılmayınca "son 500 kapanmış" penceresi SADECE eski, kötü kapanan
# pozisyonlarla dolmaya devam etti, kendi kendini besleyen bir kilitlenme
# döngüsü oluştu (5+ saat, sıfır açılış). Taban, sistemin KENDİ yeni,
# temiz verisini üretip bu döngüyü kırabilmesi için gerekli — 0 asla
# "güvenlik" değil, çıkışsız bir kilit.
MIN_MULTIPLIER = 0.1


def compute_confidence_bucket_payoff_stats() -> dict[float, dict]:
    """Gerçek kapanmış (kirli olarak işaretlenmemiş) kararlardan, beyan
    edilen (nihai, kalibre) güven kovası -> gerçek kazanma oranı + gerçek
    ortalama kazanç/kayıp büyüklüğü. confidence_calibration.py::
    compute_calibration_curve() ile AYNI sorgu/kova mantığı, ek olarak
    kazanç/kayıp büyüklüklerini de topluyor (Kelly formülü ikisine de
    ihtiyaç duyuyor, sadece win_rate'e değil).

    Faz 363 — kritik bulgu (kullanıcı isteği, gerçek veriyle doğrulandı):
    pump_fade_v1/basis_arb_v1 (AI konseyinden TAMAMEN izole, mekanik
    stratejiler, bkz. analytics/failure_classifier.py'deki AYNI izolasyon
    ilkesi) confidence alanını hiç doldurmuyor — round(confidence,1)=0.0
    kovasına 197/199 kayıt olarak yığılıyorlardı, o kovanın -$236.937
    zararının -$236.830'u (%99.9'u) TEK BAŞINA pump_fade_v1'e aitti. Bu
    sorgu bu ikisini hariç tutmuyordu — Kelly'nin confidence=0.0 kovası
    için hesapladığı istatistik AI konseyinin GERÇEK performansını değil,
    ölçüm hatasıyla karışmış pump_fade zararını yansıtıyordu."""
    from sqlalchemy import text

    from database.session_factory import SessionFactory
    from services.pump_fade_strategy import EXPERIMENT_BUCKET as _PUMP_FADE_BUCKET

    # Faz 364 — basis_arb_v1 stratejisi tamamen kaldırıldı, ama geçmişte
    # kapanmış kararları hâlâ DB'de duruyor ve izole kalmaya devam
    # etmeli — modülü tanımlayan dosya silindiği için sabit burada.
    _BASIS_ARB_BUCKET = "basis_arb_v1"

    buckets: dict[float, list[float]] = defaultdict(list)
    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                """
                SELECT confidence, pnl FROM decisions
                WHERE status = 'closed' AND excluded_from_stats = false AND confidence IS NOT NULL
                  AND (experiment_bucket IS NULL OR experiment_bucket NOT IN (:pump_fade, :basis_arb))
                """
            ),
            {"pump_fade": _PUMP_FADE_BUCKET, "basis_arb": _BASIS_ARB_BUCKET},
        ).fetchall()

    for confidence, pnl in rows:
        if confidence is None:
            continue
        bucket = round(float(confidence), 1)
        buckets[bucket].append(float(pnl or 0.0))

    stats: dict[float, dict] = {}
    for bucket, pnls in buckets.items():
        if len(pnls) < _MIN_BUCKET_SAMPLES:
            continue
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate = len(wins) / len(pnls)
        avg_win = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
        stats[bucket] = {
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "sample_count": len(pnls),
        }
    return stats


def get_confidence_bucket_payoff_stats(force_refresh: bool = False) -> dict[float, dict]:
    now = time.time()
    if (
        force_refresh
        or _cache["stats"] is None
        or (now - _cache["computed_at"]) > _CACHE_TTL_SECONDS
    ):
        try:
            _cache["stats"] = compute_confidence_bucket_payoff_stats()
        except Exception:
            # DB erişilemezse: kalibrasyon YOK sayılır (fail-closed) —
            # çarpan 1.0'a düşer, mevcut davranış değişmeden kullanılır.
            _cache["stats"] = {}
        _cache["computed_at"] = now
    return _cache["stats"]


def compute_regime_confidence_bucket_payoff_stats() -> dict[tuple[str, float], dict]:
    """Faz 290 — dış mimari inceleme raporunun (kullanıcı doğrulattı,
    2026-08-19) tek gerçek kalan bulgusu: Kelly boyutlandırma SADECE
    confidence kovasına bakıyordu, "yüksek confidence ama kötü rejim"
    durumunu hiç ayırt edemiyordu. compute_confidence_bucket_payoff_
    stats() ile AYNI sorgu/kova mantığı, ek olarak market_regime'e göre
    de gruplanıyor — decisions.market_regime (Faz 244-246'dan beri
    yazılıyor, services/position_closer.py::_extract_market_regime'in
    "trend_volatility" formatı) ile. NULL rejimli (henüz market_regime
    yazılmamış eski) kapanışlar bu kovalara hiç girmiyor — sadece gerçek
    rejim etiketli kapanışlardan öğreniliyor, icat edilmiyor."""
    from sqlalchemy import text

    from database.session_factory import SessionFactory
    from services.pump_fade_strategy import EXPERIMENT_BUCKET as _PUMP_FADE_BUCKET

    # Faz 364 — basis_arb_v1 stratejisi tamamen kaldırıldı, ama geçmişte
    # kapanmış kararları hâlâ DB'de duruyor ve izole kalmaya devam
    # etmeli — modülü tanımlayan dosya silindiği için sabit burada.
    _BASIS_ARB_BUCKET = "basis_arb_v1"

    buckets: dict[tuple[str, float], list[float]] = defaultdict(list)
    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                """
                SELECT market_regime, confidence, pnl FROM decisions
                WHERE status = 'closed' AND excluded_from_stats = false
                  AND confidence IS NOT NULL AND market_regime IS NOT NULL
                  AND (experiment_bucket IS NULL OR experiment_bucket NOT IN (:pump_fade, :basis_arb))
                """
            ),
            {"pump_fade": _PUMP_FADE_BUCKET, "basis_arb": _BASIS_ARB_BUCKET},
        ).fetchall()

    for regime, confidence, pnl in rows:
        if confidence is None or not regime:
            continue
        bucket = (regime, round(float(confidence), 1))
        buckets[bucket].append(float(pnl or 0.0))

    stats: dict[tuple[str, float], dict] = {}
    for bucket, pnls in buckets.items():
        if len(pnls) < _MIN_BUCKET_SAMPLES:
            continue
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate = len(wins) / len(pnls)
        avg_win = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
        stats[bucket] = {
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "sample_count": len(pnls),
        }
    return stats


def get_regime_confidence_bucket_payoff_stats(force_refresh: bool = False) -> dict[tuple[str, float], dict]:
    now = time.time()
    if (
        force_refresh
        or _regime_cache["stats"] is None
        or (now - _regime_cache["computed_at"]) > _CACHE_TTL_SECONDS
    ):
        try:
            _regime_cache["stats"] = compute_regime_confidence_bucket_payoff_stats()
        except Exception:
            # DB erişilemezse: rejim-özel veri YOK sayılır (fail-closed) —
            # kelly_size_multiplier confidence-only davranışına düşer.
            _regime_cache["stats"] = {}
        _regime_cache["computed_at"] = now
    return _regime_cache["stats"]


def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """Standart Kelly formülü: f* = p - q/b, b = avg_win/avg_loss (ödeme
    oranı), p = win_rate, q = 1-p. Kazanç ya da kayıp verisi yoksa (sıfır)
    hesaplanamaz -> 0.0 (bahis yapma, fail-closed). Sonuç [0,1]'e
    kırpılıyor — negatif Kelly (kenar yok/negatif EV) 0'a, teorik olarak
    1'i aşan bir değer 1'e sabitleniyor."""
    if avg_win <= 0 or avg_loss <= 0:
        return 0.0
    payoff_ratio = avg_win / avg_loss
    # Faz 324 — property-based test bulgusu: avg_win pozitif ama float
    # olarak avg_loss'a göre denormal derecede küçükse (ör. 5e-324),
    # bölüm alt taşarak (underflow) tam 0.0'a yuvarlanabiliyordu —
    # payoff_ratio>0 kontrolü olmadan aşağıdaki bölme ZeroDivisionError
    # fırlatıyordu. Gerçek veride pratik olarak imkansız bir aralık ama
    # "kazanç/kayıp verisi hesaplanamaz" durumuyla AYNI fail-closed 0.0
    # burada da geçerli.
    if payoff_ratio <= 0:
        return 0.0
    loss_rate = 1.0 - win_rate
    f = win_rate - (loss_rate / payoff_ratio)
    return max(0.0, min(f, 1.0))


def kelly_size_multiplier(confidence: float, regime: str | None = None) -> float:
    """Verilen (nihai, kalibre edilmiş) confidence'ın kovasına ait GERÇEK
    geçmiş kazanç/kayıp dağılımından half-Kelly çarpanı — [0,1] aralığında,
    her zaman mevcut tam-boyut davranışının bir KESRİ (asla üstüne
    çıkmıyor — AI kendi risk tavanını genişletemez ilkesi).

    Faz 290: `regime` verilmişse ÖNCE (regime, confidence_kovası) kovasına
    bakılıyor — yeterli örneklem varsa (>= _MIN_BUCKET_SAMPLES) bu daha
    spesifik EV tahmini kullanılıyor ("yüksek confidence ama kötü rejim"
    ayrımı). Yetersizse (ya da regime verilmemişse) ESKİ, sadece-confidence
    davranışına fail-closed düşülüyor — mevcut canlı davranış hiç
    bozulmuyor, sadece yeterli kanıt olduğunda daha keskin bir tahmine
    geçiliyor. O kova için de yeterli veri yoksa 1.0 (mevcut davranış,
    hiç küçültme yok)."""
    bucket = round(confidence, 1)
    if regime:
        regime_stats = get_regime_confidence_bucket_payoff_stats().get((regime, bucket))
        if regime_stats:
            f = kelly_fraction(regime_stats["win_rate"], regime_stats["avg_win"], regime_stats["avg_loss"])
            return max(MIN_MULTIPLIER, min(f * _HALF_KELLY_FACTOR, 1.0))

    bucket_stats = get_confidence_bucket_payoff_stats().get(bucket)
    if not bucket_stats:
        return 1.0
    f = kelly_fraction(bucket_stats["win_rate"], bucket_stats["avg_win"], bucket_stats["avg_loss"])
    half_kelly = f * _HALF_KELLY_FACTOR
    return max(MIN_MULTIPLIER, min(half_kelly, 1.0))
