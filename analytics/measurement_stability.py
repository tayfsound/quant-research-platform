"""Faz 407 (2026-09-03) — kullanıcı isteği: "biz bir şeyleri ölçüyoruz ama
verinin zaman içindeki volatilitesini ölçmüyoruz... dördüncü boyutu
hesaplarımıza dahil edelim." Gerçek bulgu, korelasyon örneğinde doğrulandı
(risk/cross_symbol_correlation.py'ye bağlı gözlem, bkz. orada): aynı
kayan-pencere yöntemiyle BTC-ETH std=0.042 (istikrarlı) vs NVDA-AMD
std=0.181 (aynı anlık okumayı üretebilir ama ~4 kat daha gürültülü, 90
pencerede 7 kez %70 eşiğini geçip-geçmiş) çıktı — TEK bir nokta tahmini
bu ikisini hiç ayırt edemiyor, ama biri güvenilir sinyal biri gürültü.

Bu modül hiçbir canlı kararı DEĞİŞTİRMİYOR/WIRE ETMİYOR — SADECE zaten
var olan geçmişten (report repository'lerin get_recent() snapshot
geçmişi, ya da canlı hesaplanan bir seri) saf bir GÖZLEM istatistiği
üretiyor. Kullanıcı kararı: "önce veriyi toplayacağız, sonra emin
olduğumuzda sıra ile wire edeceğiz" — feedback_new_complexity_must_
prove_its_edge ve feedback_incremental_module_activation ile AYNI
disiplin, sadece GÖZLEM aşaması batch, WIRE aşaması tek-tek olacak."""
from datetime import datetime
from statistics import mean, pstdev


def compute_stability(values: list[float | None]) -> dict | None:
    """values: AYNI anahtarın (ör. bir sembol çiftinin korelasyonu, bir
    kovanın win_rate'i, bir ajan-kombinasyonunun substitution_rate'i)
    zaman içindeki ardışık GERÇEK ölçümleri — kronolojik sırada olması
    gerekmiyor (mean/std sıraya duyarsız), ama HEPSİ aynı anahtarı temsil
    etmeli. En az 2 gerçek (None olmayan) değer gerekir, aksi halde
    fail-closed None döner — icat edilmiş bir stabilite skoru asla
    üretilmez (tek bir ölçüm için "stabil" ya da "oynak" demek anlamsız).

    `coefficient_of_variation` (std/|mean|) birimsiz — korelasyon gibi
    [-1,1] aralığındaki bir metrikle win_rate gibi [0,1] aralığındaki bir
    metriğin std'si doğrudan kıyaslanamaz, ama CV'leri kıyaslanabilir.
    mean==0 iken tanımsız (None) — icat edilmiş bir bölme sonucu asla
    üretilmez."""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return None
    m = mean(clean)
    s = pstdev(clean)
    # Faz 429 (2026-09-07) — kullanıcı isteği: "sign_stability" — CV'nin
    # YAKALAYAMADIĞI bir boyut. Düşük CV bile (ör. korelasyon +0.3/-0.2/
    # +0.4, std ölçekle kıyasla küçük görünebilir) işaret SÜREKLİ
    # değişiyorsa güvenilmez olabilir — CV bunu ayırt edemez. `mean`'in
    # işaretini "gerçek" kabul edip, kaç değerin AYNI işarette olduğunu
    # ölçüyor. mean==0 iken CV ile AYNI ilke: tanımsız (fail-closed None,
    # icat edilmiş bir sonuç yok) — hangi işaretin "doğru" olduğu belli
    # değil. Batch olarak TÜM mevcut *_stability çağrı noktalarına
    # otomatik uygulanıyor (yeni bir çağırma noktası eklenmedi, sadece
    # bu tek fonksiyonun döndürdüğü dict genişledi) —
    # feedback_observation_can_batch_wiring_cannot.
    if m > 0:
        sign_consistency_pct = sum(1 for v in clean if v > 0) / len(clean)
    elif m < 0:
        sign_consistency_pct = sum(1 for v in clean if v < 0) / len(clean)
    else:
        sign_consistency_pct = None
    return {
        "n": len(clean),
        "mean": m,
        "std": s,
        "min": min(clean),
        "max": max(clean),
        "coefficient_of_variation": (s / abs(m)) if m != 0 else None,
        "sign_consistency_pct": sign_consistency_pct,
    }


# Faz 415 (2026-09-06) — kullanıcı isteği: "son eklediğimiz modüllerden
# aldığımız verilerin zaman içindeki tutarlılığını gösteren verileri
# dashboard'da göremiyorum." Faz 407 kasıtlı olarak backend-only kaldı
# (gözlem-only, hiçbir dashboard kapsamda değildi) — TP/SL Confluence'ın
# (Faz 409) aynı "ölçülüyor ama görünmez" boşluğu. compute_stability()'nin
# ürettiği `*_stability` alanları her modülün kendi iç yapısında farklı
# derinliklerde gömülü (ör. `by_domain.macro.brier_score_stability`,
# `analogs[0].win_rate_stability`) — bu fonksiyon herhangi bir gather_*()
# çıktısını (Research Summary'nin zaten paralel canlı çektiği AYNI veri)
# tek tip, düz bir listeye indiriyor, yeni bir hesaplama yapmıyor.
def extract_stability_summary(result: object, _path: str = "") -> list[dict]:
    """result: herhangi bir gather_*() fonksiyonunun döndürdüğü ham dict/
    liste. Anahtarı "_stability" ile biten VE compute_stability()'nin
    şeklini taşıyan (coefficient_of_variation alanlı) her sözlüğü
    {"path", **stat} olarak düz bir listeye toplar. Liste elemanları
    ilk 20 ile sınırlı — bazı modüllerde (ör. feature_ic) yüzlerce isimli
    alt-anahtar olabiliyor, dashboard'da tek bir kart taşacak kadar
    büyümesin diye (tam veri yine de kendi sayfasında var)."""
    found: list[dict] = []
    if isinstance(result, dict):
        for key, value in result.items():
            # Gerçek bulgu: bazı modüllerin (ör. market_world_model'in
            # block_size_sensitivity.by_block_size) sözlük anahtarları
            # int (5, 10, 20, 30) — .endswith() burada patlıyordu.
            key_str = key if isinstance(key, str) else str(key)
            path = f"{_path}.{key_str}" if _path else key_str
            if key_str.endswith("_stability") and isinstance(value, dict) and "coefficient_of_variation" in value:
                found.append({"path": path, **value})
            else:
                found.extend(extract_stability_summary(value, path))
    elif isinstance(result, list):
        for i, item in enumerate(result[:20]):
            found.extend(extract_stability_summary(item, f"{_path}[{i}]"))
    return found


# Faz 431 (2026-09-07) — kullanıcı isteği: "non-overlapping window
# stability"nin araştırma bulgusu. Gerçek snapshot geçmişi ölçüldü:
# `market_state_gatherer.py`'nin `correlation_stability`'si ~18dk kadansla
# kaydediliyor ama 250 mumluk (15dk zaman diliminde ~2,6 gün) kayan bir
# pencereden hesaplanıyor — ardışık iki snapshot ~%99+ aynı ham veriyi
# paylaşıyor, CV'nin öne sürdüğü "istikrar" büyük ölçüde otokorelasyon.
# Bu fonksiyon, ham snapshot geçmişinden GERÇEKTEN bağımsız (pencere
# uzunluğu kadar aralıklı) bir alt-küme seçiyor — en yeniden geriye doğru
# açgözlü (greedy) seçim, `min_spacing_minutes`'tan daha yakın olan her
# aday atlanıyor. Yeterli geçmiş yoksa (mevcut durum — correlation_
# snapshots'ta sadece ~4 günlük veri var, 2,6 günlük pencereyle 12
# bağımsız nokta için ~31 gün gerekir) az sayıda (hatta 1) sonuç döner —
# icat edilmiş bir nokta asla üretilmez, veri zamanla organik olarak
# birikince nokta sayısı kendiliğinden artar.
def select_non_overlapping_snapshots(
    snapshots: list[dict], min_spacing_minutes: float, created_at_key: str = "created_at",
    limit: int | None = None,
) -> list[dict]:
    """snapshots: `created_at_key`'i ISO-format bir zaman damgası (string)
    olan sözlükler, HERHANGİ bir sırada olabilir (önce kronolojik olarak
    en yeniden en eskiye sıralanır). min_spacing_minutes <= 0 ise TÜM
    snapshot'lar döner (spacing kontrolü anlamsız — no-op)."""
    if min_spacing_minutes <= 0:
        return list(snapshots) if limit is None else list(snapshots)[:limit]

    dated = []
    for snap in snapshots:
        raw = snap.get(created_at_key)
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(raw) if isinstance(raw, str) else raw
        except ValueError:
            continue
        dated.append((ts, snap))
    dated.sort(key=lambda item: item[0], reverse=True)

    selected: list[dict] = []
    last_ts = None
    for ts, snap in dated:
        if last_ts is None or (last_ts - ts).total_seconds() / 60.0 >= min_spacing_minutes:
            selected.append(snap)
            last_ts = ts
            if limit is not None and len(selected) >= limit:
                break
    return selected
