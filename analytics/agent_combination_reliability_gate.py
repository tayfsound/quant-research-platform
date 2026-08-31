"""Ajan Kombinasyonu Güvenilirliği Kapısı — Faz 367-devam, kullanıcı isteği
(2026-08-28): "kararı vermeden önce burayı tarayacak, ajan gruplarının
başarısını ölçecek — %80'in altında kalıyorsa pozisyonu açmayacak."

analytics/agent_combination_reliability.py'nin HAFTALIK ürettiği rapordaki
(services/tasks.py::refresh_agent_combination_reliability_report_task,
AgentCombinationReliabilityReportRepository) gruplar, gerçek zamanlı bir
karar anında o kararın kendi agreeing_domains kümesiyle karşılaştırılır.
Rapor her kararda YENİDEN hesaplanmıyor (kadar 2000 kapanmış işlemi taraması
gerekiyor, karar döngüsü için çok pahalı olurdu) — haftalık anlık görüntü
kullanılıyor, diğer periyodik-sınıflandırmalı kapılarla (ör. pivot_
distance_gate) AYNI ilke.

SADECE gerçekten kanıtlanmış (fdr_significant) VE bağımsız (düşük
max_shared_trade_overlap_pct — aksi halde aynı işlemlerin tekrar sayımı
"kanıt" gibi görünebilirdi, bkz. agent_combination_reliability.py'nin
kendi notu) gruplar "bilinen" sayılır. Diğer tüm aç-kapa kapılarıyla
(regime_trading_gate/mae_mfe_bucket_trading_gate) AYNI fail-open ilkesi:
rapor yoksa/eşleşen bilinen bir grup yoksa ASLA engellemez — kullanıcı
tercihi kapısı, güvenlik kapısı değil.

Kapsamlı NOT: uzun süre SADECE engelleme (blok) yönü vardı — "iyi bilinen
bir grup pozisyonu güçlendirsin/zorunlu kılsın" yönü kasıtlı olarak
ERTELENMİŞTİ (kullanıcı isteği, adım adım aktivasyon ilkesi — önce blok
yönünün gerçekten iyi çalıştığı gözlemlensin). Faz 392 (2026-08-31) ile
bu ikinci yarı da (force_open_eligible_pairs / is_agent_combination_
force_eligible, aşağıda) kullanıcı onayıyla devreye alındı — DAHA SIKI
bir kanıt eşiğiyle (gate_eligible + yüksek win_rate, sadece bağımsızlık
değil)."""

# Kullanıcı bulgusu (2026-08-28): gerçek veride genel ortalama (baseline)
# win_rate ~%74 civarında oturuyor, bunun altındaki gruplar dashboard'da
# tutarlı şekilde zarara işaret ediyor (baseline'a göre negatif fark).
DEFAULT_MIN_WIN_RATE = 0.74
DEFAULT_MAX_OVERLAP_PCT = 0.50
# Faz 368 — kullanıcı bulgusu (GPT incelemesi + canlı doğrulama): örtüşme
# eşiği TEK BAŞINA yetmiyor — farklı domain kombinasyonlarına sahip iki
# grup (düşük overlap) yine de AYNI dar tarihsel pencereden (ör. tek bir
# ~42 saatlik ralli) gelip "bağımsız kanıt" gibi görünebiliyordu (bkz.
# agent_combination_reliability.py'nin pattern+sentiment n=166 örneği —
# 166 işlemin TAMAMI 20-22 Ağustos'tan). En az bu kadar FARKLI takvim
# gününe yayılmayan bir grup "kanıtlanmış" sayılmaz — dar bir rejim/olay
# artefaktını "sinerji" sanmayı engellemek için.
DEFAULT_MIN_DISTINCT_DAYS = 5


def trustworthy_known_pairs(
    report_pairs: list[dict],
    max_overlap_pct: float = DEFAULT_MAX_OVERLAP_PCT,
    min_distinct_days: int = DEFAULT_MIN_DISTINCT_DAYS,
) -> list[dict]:
    """Rapordaki TÜM gruplardan, gerçekten bağımsız kanıt sayılabilecek
    (FDR'ı geçmiş VE örtüşmesi düşük VE yeterince geniş bir zaman
    aralığına yayılmış) alt kümeyi çıkarır — kapı fonksiyonu SADECE bu alt
    kümeye bakar, ham rapor asla doğrudan kullanılmaz. distinct_days
    bilinmiyorsa (eski/kayıp closed_at verisi) fail-closed dışlanır —
    "kanıtlanmış" varsayılan durum değil, ispat gerekir."""
    return [
        p for p in report_pairs
        if p.get("fdr_significant")
        and p.get("max_shared_trade_overlap_pct", 1.0) < max_overlap_pct
        and (p.get("distinct_days") or 0) >= min_distinct_days
    ]


def is_agent_combination_trading_blocked(
    agreeing_domains: frozenset[str] | None,
    known_pairs: list[dict],
    min_win_rate: float = DEFAULT_MIN_WIN_RATE,
) -> bool:
    """agreeing_domains: bu kararda nihai yönle AYNI yönde oy veren
    domain'ler (agent_combination_reliability.py::agreeing_domains_for_
    decision). known_pairs: trustworthy_known_pairs()'ın çıktısı — HER
    bilinen grup, kararın agreeing_domains'inin bir ALT KÜMESİYSE (yani o
    grup GERÇEKTEN bu kararda anlaşmışsa) ve o grubun geçmiş win_rate'i
    min_win_rate'in altındaysa, karar engellenir. Birden fazla bilinen
    grup eşleşirse TEK bir düşük performanslı eşleşme yeterli (en
    kötümser/en güvenli varsayım — "iyi bir grup de vardı" bahanesiyle
    bilinen kötü bir grubu görmezden gelmiyoruz)."""
    if agreeing_domains is None:
        return False
    for pair in known_pairs:
        if set(pair["domains"]) <= agreeing_domains and pair["win_rate"] < min_win_rate:
            return True
    return False


# Faz 392 — kullanıcı isteği (2026-08-31): "Daha önce başarılı olmuş
# rejimler ve ajan kombinasyonu gibi bir araya gelen durumlar olursa
# sistem hiçbir engele takılmasın direkt işlem açsın." Bu yukarıdaki blok
# yönünün AYNEN simetriği — dosyanın en üstündeki docstring'de (satır
# 22-25) zaten "kasıtlı olarak ERTELENDİ" diye kayıtlı ikinci yarı, şimdi
# kullanıcı onayıyla devreye alınıyor.
#
# Faz 392 düzeltme (aynı gün) — kullanıcı ilk versiyondaki sabit %85
# eşiğine itiraz etti: "Onların güvenilmez olduklarına ne kadar eminiz?
# ... aynı hayatı yüz defa yaparım ki hata olduğuna emin olabileyim."
# Ayrı bir force-open eşiği YOK artık — win_rate bar'ı DOĞRUDAN
# kullanıcının panelden kontrol ettiği blok kapısının kendi eşiğine
# (`agent_combination_gate_min_win_rate`) bağlı: kapı KAPALIYSA (kullanıcı
# zaten "güvenilir/güvenilmez" ayrımını istemiyor demektir) win_rate
# filtresi tamamen devre dışı (min_win_rate=0.0, hepsi geçer) — SADECE
# `gate_eligible` (FDR + OOS-survival + yeterli örneklem) kalır, çünkü bu
# "güvenilmez" demek değil, "yeterince tekrar edilmedi, henüz bir şey
# söylenemez" demek (kullanıcının kendi "yüz kere yaşama" mantığı).
def force_open_eligible_pairs(
    report_pairs: list[dict],
    min_win_rate: float = 0.0,
    max_overlap_pct: float = DEFAULT_MAX_OVERLAP_PCT,
    min_distinct_days: int = DEFAULT_MIN_DISTINCT_DAYS,
) -> list[dict]:
    """trustworthy_known_pairs()'ın (bağımsızlık kanıtı) çıktısını, AYRICA
    gate_eligible (FDR-anlamlı + OOS-survival + yeterli effective_sample_
    size — analytics/agent_combination_reliability.py'nin kendi üç-şartlı
    bayrağı) VE win_rate >= min_win_rate ile daraltır. min_win_rate=0.0
    (varsayılan) demek: win_rate hiç filtrelenmiyor, sadece gate_eligible
    yeterli — çağıran taraf (services/decision_fusion.py) bunu kullanıcının
    panel eşiğine göre belirler."""
    known = trustworthy_known_pairs(report_pairs, max_overlap_pct, min_distinct_days)
    return [p for p in known if p.get("gate_eligible") and p["win_rate"] >= min_win_rate]


def is_agent_combination_force_eligible(
    agreeing_domains: frozenset[str] | None,
    known_pairs: list[dict],
) -> tuple[bool, dict | None]:
    """is_agent_combination_trading_blocked ile simetrik eşleştirme
    mantığı: known_pairs = force_open_eligible_pairs()'ın çıktısı. Birden
    fazla eşleşme varsa en yüksek win_rate'li olan audit için döndürülür
    (blok yönünün "en kötümser" ilkesinin tersi — burada en güçlü kanıtı
    göstermek audit açısından daha faydalı, karar zaten TEK bir eşleşmeyle
    veriliyor)."""
    if agreeing_domains is None:
        return False, None
    matches = [p for p in known_pairs if set(p["domains"]) <= agreeing_domains]
    if not matches:
        return False, None
    best = max(matches, key=lambda p: p["win_rate"])
    return True, best
