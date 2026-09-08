"""Council vs Historical Analog Uzlaşım Raporu — Faz 452 (2026-09-08).
Faz 447'nin ("Council'in evidence-provider'a geçişi") kullanıcı onaylı
İLK, en güvenli adımı: hiçbir canlı davranış DEĞİŞMİYOR, sadece gerçek
soruya gerçek veriyle cevap veriliyor — "gate_eligible bir tarihsel
analog VARSA, o bağlamdaki kararlar GERÇEKTEN daha mı iyi sonuç veriyor,
yoksa Council'in kendi kararından farksız mı?"

Bağlam: bugünkü bulgular (Faz 446/448) Faz 447'nin kendi tetikleme
koşulunu ("AI/Council baseline'ları GERÇEKTEN geçtiğini göstermeden bu
faza girilmeyecek") TERSİNE doğruladı — AI direction Brier'i randomdan
kötü. Bu, Council'i hemen yeniden tasarlamak için yeterli kanıt DEĞİL
(tek yönlü bir gözlem, tersine mühendislik riskli) — önce tarihsel
analog motorunun GERÇEKTEN öngörü değeri taşıyıp taşımadığı, TAMAMEN
tutulmuş (held-out) gerçek veriyle test edilmeli. `gate_eligible`
etiketinin kendi OOS koruması (agent_combination_reliability.py) var
ama bu, AYNI 2000-8000 kararlık pencerenin İÇİNDE erken/geç bölünmesi —
gerçekten YENİ, o pencere hesaplanırken hiç var olmayan kararlarla test
etmek daha sıkı bir kanıt standardı."""

DEFAULT_MIN_HOLDOUT_SAMPLE = 10


def _analog_matches(analog: dict, record: dict) -> bool:
    """Bir gate_eligible analog hücresinin bir held-out kararla eşleşip
    eşleşmediği — domains ÜST KÜME ilişkisi (compute_historical_analogs()
    ile AYNI mantık), diğer 6 boyut TAM eşleşme."""
    if not set(analog["domains"]) <= record.get("agreeing_domains", frozenset()):
        return False
    return (
        analog["market_regime"] == record.get("market_regime")
        and analog["direction"] == record.get("direction")
        and analog["reversing"] == record.get("reversing")
        and analog["volatility_regime"] == record.get("volatility_regime")
        and analog["structure_phase"] == record.get("structure_phase")
        and analog["trade_type"] == record.get("trade_type")
    )


def compute_council_vs_analog_agreement(
    gate_eligible_analogs: list[dict],
    holdout_records: list[dict],
    min_holdout_sample: int = DEFAULT_MIN_HOLDOUT_SAMPLE,
) -> dict | None:
    """gate_eligible_analogs: `compute_historical_analogs()`'un
    `analogs` listesinden SADECE `gate_eligible=True` olanlar (çağıran
    filtreler — bu fonksiyon kendisi filtrelemiyor, tek sorumluluk).
    holdout_records: analog raporunun hesaplandığı pencereden TAMAMEN
    SONRAKİ, GERÇEKTEN yeni kapanmış kararlar (her biri {'agreeing_
    domains', 'market_regime', 'direction', 'reversing', 'volatility_
    regime', 'structure_phase', 'trade_type', 'win'}).

    Her held-out kararı, EN AZ bir gate_eligible hücreyle eşleşiyor mu
    diye kontrol eder ('analog_endorsed' grup) — eşleşmiyorsa 'other'
    grubuna girer (bu grup ZATEN Council'in kendi kararlarının geri
    kalanı, ayrı bir "Council kararı" kavramı YOK — Council HER İKİ
    grubu da açmış, soru "analog'un işaret ettiği alt küme gerçekten
    daha mı iyi çıkıyor"). <min_holdout_sample eşleşen kararla fail-
    closed None (icat edilmiş bir karşılaştırma asla üretilmez)."""
    if not gate_eligible_analogs:
        return None

    endorsed = []
    other = []
    for r in holdout_records:
        if r.get("win") is None:
            continue
        matched = any(_analog_matches(a, r) for a in gate_eligible_analogs)
        (endorsed if matched else other).append(r)

    if len(endorsed) < min_holdout_sample:
        return None

    def _win_rate(records: list[dict]) -> float | None:
        return round(sum(1 for r in records if r["win"]) / len(records), 4) if records else None

    endorsed_win_rate = _win_rate(endorsed)
    other_win_rate = _win_rate(other)

    return {
        "n_gate_eligible_analogs": len(gate_eligible_analogs),
        "n_endorsed": len(endorsed),
        "n_other": len(other),
        "endorsed_win_rate": endorsed_win_rate,
        "other_win_rate": other_win_rate,
        "lift": (
            round(endorsed_win_rate - other_win_rate, 4)
            if endorsed_win_rate is not None and other_win_rate is not None
            else None
        ),
    }
