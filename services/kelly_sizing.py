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

_MIN_BUCKET_SAMPLES = 20
_CACHE_TTL_SECONDS = 300
_HALF_KELLY_FACTOR = 0.5
_cache: dict = {"stats": None, "computed_at": 0.0}


def compute_confidence_bucket_payoff_stats() -> dict[float, dict]:
    """Gerçek kapanmış (kirli olarak işaretlenmemiş) kararlardan, beyan
    edilen (nihai, kalibre) güven kovası -> gerçek kazanma oranı + gerçek
    ortalama kazanç/kayıp büyüklüğü. confidence_calibration.py::
    compute_calibration_curve() ile AYNI sorgu/kova mantığı, ek olarak
    kazanç/kayıp büyüklüklerini de topluyor (Kelly formülü ikisine de
    ihtiyaç duyuyor, sadece win_rate'e değil)."""
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    buckets: dict[float, list[float]] = defaultdict(list)
    with SessionFactory.get_session() as session:
        rows = session.execute(text(
            """
            SELECT confidence, pnl FROM decisions
            WHERE status = 'closed' AND excluded_from_stats = false AND confidence IS NOT NULL
            """
        )).fetchall()

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


def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """Standart Kelly formülü: f* = p - q/b, b = avg_win/avg_loss (ödeme
    oranı), p = win_rate, q = 1-p. Kazanç ya da kayıp verisi yoksa (sıfır)
    hesaplanamaz -> 0.0 (bahis yapma, fail-closed). Sonuç [0,1]'e
    kırpılıyor — negatif Kelly (kenar yok/negatif EV) 0'a, teorik olarak
    1'i aşan bir değer 1'e sabitleniyor."""
    if avg_win <= 0 or avg_loss <= 0:
        return 0.0
    payoff_ratio = avg_win / avg_loss
    loss_rate = 1.0 - win_rate
    f = win_rate - (loss_rate / payoff_ratio)
    return max(0.0, min(f, 1.0))


def kelly_size_multiplier(confidence: float) -> float:
    """Verilen (nihai, kalibre edilmiş) confidence'ın kovasına ait GERÇEK
    geçmiş kazanç/kayıp dağılımından half-Kelly çarpanı — [0,1] aralığında,
    her zaman mevcut tam-boyut davranışının bir KESRİ (asla üstüne
    çıkmıyor — AI kendi risk tavanını genişletemez ilkesi). O kova için
    yeterli veri yoksa 1.0 (mevcut davranış, hiç küçültme yok)."""
    bucket = round(confidence, 1)
    bucket_stats = get_confidence_bucket_payoff_stats().get(bucket)
    if not bucket_stats:
        return 1.0
    f = kelly_fraction(bucket_stats["win_rate"], bucket_stats["avg_win"], bucket_stats["avg_loss"])
    half_kelly = f * _HALF_KELLY_FACTOR
    return max(0.0, min(half_kelly, 1.0))
