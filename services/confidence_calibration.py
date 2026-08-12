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
    Eğri boşsa (yeterli veri yok) ham değeri DEĞİŞTİRMEDEN döner — icat
    edilmiş bir düzeltme değil.

    Faz 268r — kritik bulgu: raw_confidence, eğrinin en üst noktasının
    (curve[-1][0]) ÜZERİNDEYSE (ör. eğri 0.6'da bitiyor ama raw=0.85
    geldi), önceki hal ham değeri DEĞİŞMEDEN döndürüyordu — yani DecisionFusion'ın
    EV hesabı, gerçek veriyle HİÇ doğrulanmamış bir güveni aynen
    kullanıyordu. Bu tam olarak Faz248'in çözmeye çalıştığı sorunun
    (beyan edilen güven şişkin) en tehlikeli ucuydu — yüksek beyan edilen
    güven daha büyük pozisyon demek, ve bu bölgede hiç kalibrasyon
    uygulanmıyordu. Artık eğrinin dışına taşan ÜST uç, eğrinin bildiği EN
    SON gerçek orana sabitleniyor (curve[-1][1]) — bu bir icat değil,
    elimizdeki EN YAKIN gerçek gözlem: "bu kadar yüksek bir güven
    bölgesinde, gördüğümüz en iyi gerçek kazanma oranı bile şu kadardı."
    ALT uç (raw_confidence <= curve[0][0]) kasıtlı olarak DEĞİŞTİRİLMEDEN
    bırakılıyor — zaten düşük bir değeri daha da aşağı çekmenin (ya da
    icat edilmiş bir taban vermenin) EV gate'i yanlış yönde etkileme
    riski yok, mevcut davranış zaten güvenli tarafta."""
    if curve is None:
        curve = get_calibration_curve()
    if not curve:
        return raw_confidence

    if raw_confidence <= curve[0][0]:
        return curve[0][1] if raw_confidence == curve[0][0] else raw_confidence
    if raw_confidence >= curve[-1][0]:
        return curve[-1][1]

    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if x0 <= raw_confidence <= x1:
            if x1 == x0:
                return y0
            t = (raw_confidence - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)

    return raw_confidence


# Faz 268al — "İsabeti artırmanın yolu daha akıllı kullanım" yol
# haritasının A fazı (Confidence Kalibrasyonu). compute_calibration_curve()
# yukarıda TEK bir (council-sonrası, fused) eğri üretiyor — DecisionFusion'ın
# EV hesabını düzeltiyor ama BeliefEngine'in oy ağırlıklandırması
# (AgentOpinion.effective_influence, her ajanın KENDİ ham confidence'ını
# kullanıyor, bkz. contracts/agent.py::recalculate) hâlâ kalibre edilmemiş
# sayılarla çalışıyordu — yani 9 ajanın oyu birleştirilirken, hangi ajanın
# ne kadar "haklı çıktığı" hiç doğrulanmamış ham beyanlarla ölçülüyordu.
# Buradaki fonksiyonlar her ajan domain'i için AYRI bir eğri üretir —
# AgentMemory'deki gerçek (confidence, was_correct) çiftlerinden, YUKARIDAKİ
# ile AYNI ampirik-kova + doğrusal enterpolasyon yöntemiyle (icat edilmiş
# bir model/logistic regression değil — bu kod tabanının zaten kanıtlanmış
# yaklaşımı, ek bir bağımlılık/overfit riski olmadan).
_DOMAIN_MIN_BUCKET_SAMPLES = 20
_domain_cache: dict = {"curves": None, "computed_at": 0.0}


def compute_domain_calibration_curves(memory=None) -> dict[str, list[tuple[float, float]]]:
    """Her ajan domain'i için, GERÇEKTEN yönlü (LONG/SHORT) oy verdiği
    kayıtlardan beyan edilen güven kovası -> gerçekten doğru çıkma oranı
    eğrisi. WAIT kayıtları (time/epistemology'nin tasarım gereği her
    zaman verdiği oy) dahil edilmez — bir tahmin değil, doğru/yanlış
    ölçülemez (Faz245 ile aynı ilke). Yeterli örneklemi olmayan domain'ler
    (ör. bu yüzden time/epistemology) boş eğriyle kalır — fail-closed.

    `memory` parametresi (varsayılan AgentMemory()) testlerin gerçek
    (paylaşılan, tüm test oturumu boyunca biriken) agent_memory dosyasına
    dokunmadan izole bir AgentMemory enjekte edebilmesi için — bkz.
    backtest/real_historical_backtest.py::_record_backtest_agent_learning
    ile aynı desen."""
    from collections import defaultdict

    from services.agent_memory import AgentMemory

    memory = memory or AgentMemory()
    curves: dict[str, list[tuple[float, float]]] = {}

    for domain in memory.domains():
        buckets: dict[float, list[float]] = defaultdict(list)
        for record in memory._records.get(domain, []):
            if record.direction.upper() not in ("LONG", "SHORT"):
                continue
            bucket = round(record.confidence, 1)
            buckets[bucket].append(1.0 if record.was_correct else 0.0)

        curve = []
        for bucket, outcomes in sorted(buckets.items()):
            if len(outcomes) < _DOMAIN_MIN_BUCKET_SAMPLES:
                continue
            curve.append((bucket, sum(outcomes) / len(outcomes)))
        if curve:
            curves[domain] = curve

    return curves


def get_domain_calibration_curves(force_refresh: bool = False) -> dict[str, list[tuple[float, float]]]:
    now = time.time()
    if (
        force_refresh
        or _domain_cache["curves"] is None
        or (now - _domain_cache["computed_at"]) > _CACHE_TTL_SECONDS
    ):
        try:
            _domain_cache["curves"] = compute_domain_calibration_curves()
        except Exception:
            # AgentMemory dosyası okunamazsa: kalibrasyon YOK sayılır
            # (fail-closed) — ham güven değerleri değişmeden kullanılır.
            _domain_cache["curves"] = {}
        _domain_cache["computed_at"] = now
    return _domain_cache["curves"]


# Faz 268e — gerçek bulgu: kalibrasyon eğrisi bir kova için "geçmişte bu
# ham güveni beyan eden kararların ortalaması X kez doğru çıktı" diyor,
# ama TEK bir kararın o ortalamayı ne kadar temsil ettiği kanıt sayısına
# göre çok değişir. Canlıda doğrulandı: quant_agent'ın TEK kanıtlı
# (sadece "200-EMA bear trend"), ham %25 güvenli bir SHORT kararı,
# kalibrasyonla %77.5'e şişti — o kovadaki geçmiş kararların ÇOĞU
# muhtemelen birden fazla kanıta dayanıyordu, ama kalibrasyon "kaç kanıt
# var" diye hiç bakmıyordu. Artık az kanıtlı kararlarda kalibrasyonun
# düzeltmesi (raw'dan ne kadar uzaklaştığı) kanıt sayısına göre
# yumuşatılıyor — icat edilmiş bir ağırlık değil, "3+ kanıt varsa tam
# güven, daha azsa orantılı" gibi en basit, açıklanabilir kural.
_FULL_TRUST_EVIDENCE_COUNT = 3


def calibrate_domain_confidence(
    domain: str, raw_confidence: float, evidence_count: int | None = None
) -> float:
    """Bir ajanın KENDİ domain'ine ait ampirik eğrisinden geçirir —
    calibrate_confidence()'ın üst/alt uç mantığı (fail-closed alt uç,
    en-son-gözleme-sabitleme üst uç) burada da aynen geçerli. O domain
    için yeterli veri yoksa ham değeri değiştirmeden döner.

    evidence_count verilirse (bkz. AgentOpinion.evidence — o kararın kaç
    ayrı sinyale dayandığı), kalibrasyonun ham değerden ne kadar
    uzaklaştığı bu sayıya göre yumuşatılır — 3+ kanıtta tam kalibrasyon,
    daha azında orantılı olarak daha az. evidence_count verilmezse
    (varsayılan None) eski davranış aynen korunur — tam kalibrasyon."""
    curve = get_domain_calibration_curves().get(domain)
    if not curve:
        return raw_confidence
    calibrated = calibrate_confidence(raw_confidence, curve=curve)
    if evidence_count is None:
        return calibrated
    trust = min(max(evidence_count, 0) / _FULL_TRUST_EVIDENCE_COUNT, 1.0)
    return raw_confidence + (calibrated - raw_confidence) * trust
