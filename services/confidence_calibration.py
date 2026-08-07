"""Faz 248: kullanıcı isteği — ajanların/karar motorunun beyan ettiği
"güven" hiç doğrulanmıyordu. Gerçek veriyle ölçüldü: decisions.confidence
(DecisionFusion'ın EV formülünde — `ev = confidence*win - (1-confidence)*loss`
— doğrudan kullandığı sayı) sistemli olarak ŞİŞİRİLMİŞ — beyan edilen
%40-60 güven aralığında GERÇEK kazanma oranı %21-33 (yani 20-24 yüzde
puan daha düşük). Bu, EV hesabının kayıp getirecek işlemleri "pozitif EV"
sanmasına yol açıyor — muhtemelen sistemin genel düşük kazanma oranının
(%23.6) doğrudan bir nedeni.

Kök nedenini (metacognition/debate synthesis'in içindeki tam mekanizma)
yeniden yazmak yerine — daha güvenli, daha kolay doğrulanabilir bir
düzeltme: gerçek geçmiş kararlardan ampirik bir kalibrasyon eğrisi
(beyan edilen güven -> gerçekten gözlenen kazanma oranı) çıkarıp,
DecisionFusion'a giden HER confidence değerini bu eğriden geçiriyoruz.
Yeterli örneklem yoksa (fail-closed, fail-fake değil) HİÇBİR düzeltme
uygulanmıyor — ham değer aynen kullanılıyor."""
import time

_MIN_BUCKET_SAMPLES = 20
_CACHE_TTL_SECONDS = 300
_cache: dict = {"curve": None, "computed_at": 0.0}


def compute_calibration_curve() -> list[tuple[float, float]]:
    """Gerçek kapanmış (ve kirli olarak işaretlenmemiş) kararlardan,
    beyan edilen güven kovası -> gerçekten gözlenen kazanma oranı eğrisi.
    Sadece yeterli örneklemi (>= _MIN_BUCKET_SAMPLES) olan kovalar
    dahil edilir."""
    from collections import defaultdict

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
        buckets[bucket].append(1.0 if (pnl or 0.0) > 0 else 0.0)

    curve = []
    for bucket, outcomes in sorted(buckets.items()):
        if len(outcomes) < _MIN_BUCKET_SAMPLES:
            continue
        curve.append((bucket, sum(outcomes) / len(outcomes)))
    return curve


def get_calibration_curve(force_refresh: bool = False) -> list[tuple[float, float]]:
    now = time.time()
    if force_refresh or _cache["curve"] is None or (now - _cache["computed_at"]) > _CACHE_TTL_SECONDS:
        try:
            _cache["curve"] = compute_calibration_curve()
        except Exception:
            # DB erişilemezse ya da tablo henüz yoksa: kalibrasyon YOK
            # sayılır (fail-closed) — ham güven değeri değişmeden kullanılır.
            _cache["curve"] = []
        _cache["computed_at"] = now
    return _cache["curve"]


def calibrate_confidence(raw_confidence: float, curve: list[tuple[float, float]] | None = None) -> float:
    """raw_confidence'ı ampirik eğriden geçirir (doğrusal enterpolasyon).
    Eğri boşsa (yeterli veri yok) ya da raw_confidence eğrinin dışındaysa,
    ham değeri DEĞİŞTİRMEDEN döner — icat edilmiş bir düzeltme değil."""
    if curve is None:
        curve = get_calibration_curve()
    if not curve:
        return raw_confidence

    if raw_confidence <= curve[0][0]:
        return curve[0][1] if raw_confidence == curve[0][0] else raw_confidence
    if raw_confidence >= curve[-1][0]:
        return curve[-1][1] if raw_confidence == curve[-1][0] else raw_confidence

    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if x0 <= raw_confidence <= x1:
            if x1 == x0:
                return y0
            t = (raw_confidence - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)

    return raw_confidence
