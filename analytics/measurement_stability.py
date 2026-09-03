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
    return {
        "n": len(clean),
        "mean": m,
        "std": s,
        "min": min(clean),
        "max": max(clean),
        "coefficient_of_variation": (s / abs(m)) if m != 0 else None,
    }
