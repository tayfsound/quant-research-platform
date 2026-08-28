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

Kapsamlı NOT: şimdilik SADECE engelleme (blok) yönü var — "iyi bilinen bir
grup pozisyonu güçlendirsin/zorunlu kılsın" yönü kasıtlı olarak
ERTELENDİ (kullanıcı isteği, adım adım aktivasyon ilkesi — önce blok
yönünün gerçekten iyi çalıştığı gözlemlensin)."""

# Kullanıcı bulgusu (2026-08-28): gerçek veride genel ortalama (baseline)
# win_rate ~%74 civarında oturuyor, bunun altındaki gruplar dashboard'da
# tutarlı şekilde zarara işaret ediyor (baseline'a göre negatif fark).
DEFAULT_MIN_WIN_RATE = 0.74
DEFAULT_MAX_OVERLAP_PCT = 0.50


def trustworthy_known_pairs(
    report_pairs: list[dict],
    max_overlap_pct: float = DEFAULT_MAX_OVERLAP_PCT,
) -> list[dict]:
    """Rapordaki TÜM gruplardan, gerçekten bağımsız kanıt sayılabilecek
    (FDR'ı geçmiş VE örtüşmesi düşük) alt kümeyi çıkarır — kapı fonksiyonu
    SADECE bu alt kümeye bakar, ham rapor asla doğrudan kullanılmaz."""
    return [
        p for p in report_pairs
        if p.get("fdr_significant") and p.get("max_shared_trade_overlap_pct", 1.0) < max_overlap_pct
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
