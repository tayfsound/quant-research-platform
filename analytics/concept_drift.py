"""Online Learning ve Concept Drift — Faz 719-743 (Cognitive Core 2.0 / M9).

analytics/model_drift.py FEATURE dağılımlarındaki (P(X)) kaymayı
(PSI/KS-test) tespit ediyor — ama bu, feature İLE SONUÇ arasındaki
İLİŞKİNİN (P(Y|X), "concept") değiştiğini YAKALAMAZ: aynı RSI değeri dün
"al" sinyaliydi, bugün piyasa rejimi değiştiği için "sat" sinyaline
dönüşmüş olabilir — feature'ın kendisi hiç kaymamış olsa bile. Bu modül,
standart bir istatistiksel test (2x2 ki-kare bağımsızlık testi) ile bir
ajanın/modelin GERÇEK doğruluk oranının iki zaman penceresi arasında
anlamlı şekilde değişip değişmediğini tespit ediyor — icat edilmiş bir
eşik değil.

Kasıtlı olarak SADECE tespit/rapor — hiçbir ajan ağırlığını/kararını
burada otomatik değiştirmiyor."""
from scipy import stats

MIN_SAMPLE_SIZE = 20
SIGNIFICANCE_LEVEL = 0.05


def collapse_batch_closed_trades(trades: list[dict]) -> list[dict]:
    """Faz 398 (2026-09-01) — gerçek olay: 2026-08-27'de GC=F+XAUTUSDT
    (aynı temel varlık, altın) için açılan bir piramit kümesi (aynı
    dakikalarda 5-10 ayrı giriş) `close_due_positions()`'ın TEK bir
    taramasında (services/position_closer.py — `now = datetime.now(UTC)`
    döngü başında BİR KEZ hesaplanıp tüm bacaklara uygulanıyor) hep
    birlikte kapandı — Concept Drift'in "son 50 işlem" penceresinin
    %40'ını (20/50), TEK bir gerçek ticaret tezini onlarca kez sayarak
    doldurdu (baseline %66 → recent %26, p=8.5e-6 — istatistiksel olarak
    "anlamlı" ama gerçekte büyük ölçüde bir sayım artefaktı).

    `trades`: `DecisionPersistor.list_closed_trades()`'in döndürdüğü,
    closed_at DESC sıralı ham satırlar (`{"symbol", "closed_at", "pnl",
    ...}`). Aynı sembolün aynı ANDA (aynı `closed_at`, yani aynı tarama
    olayında) kapanan bacaklarını TEK bir "karar" a indirger — toplam pnl
    (win = toplam pnl > 0). Farklı sembollerin aynı taramada kapanması
    (ilgisiz, ayrı tezler) ayrı kalır — anahtar (symbol, closed_at) ikilisi.
    Aynı sembolün farklı ZAMANLARDA (ör. günler arayla) kapanan bacakları
    KASITLI OLARAK birleştirilmiyor — bunlar gerçekten ayrı karar anları
    (her biri kendi zamanında sistemin pozisyonu açık bırakma/kapatma
    kararı), tek bir sayım artefaktı değil."""
    groups: dict[tuple, dict] = {}
    order: list[tuple] = []
    for t in trades:
        key = (t.get("symbol"), t.get("closed_at"))
        if key not in groups:
            groups[key] = {"symbol": t.get("symbol"), "closed_at": t.get("closed_at"), "pnl": 0.0, "leg_count": 0}
            order.append(key)
        groups[key]["pnl"] += t.get("pnl") or 0.0
        groups[key]["leg_count"] += 1
    return [groups[k] for k in order]


def compute_concept_drift(
    baseline_outcomes: list[bool],
    recent_outcomes: list[bool],
) -> dict | None:
    """baseline_outcomes/recent_outcomes: GERÇEK win/loss (True/False)
    sonuçları, iki AYRI zaman penceresinden (ör. bir ajanın 200 işlem
    önceki ve son 50 işlemdeki gerçek doğruluğu). 2x2 ki-kare bağımsızlık
    testiyle doğruluk oranının anlamlı şekilde değişip değişmediğini
    kontrol eder. <MIN_SAMPLE_SIZE her iki pencerede de olmalı; testin
    matematiksel olarak tanımsız kaldığı dejenere durumlarda (ör. bir
    hücre grubu sürekli sıfır) fail-closed None döner — icat edilmiş bir
    p-value asla üretilmez."""
    if len(baseline_outcomes) < MIN_SAMPLE_SIZE or len(recent_outcomes) < MIN_SAMPLE_SIZE:
        return None

    baseline_wins = sum(baseline_outcomes)
    baseline_losses = len(baseline_outcomes) - baseline_wins
    recent_wins = sum(recent_outcomes)
    recent_losses = len(recent_outcomes) - recent_wins

    contingency = [[baseline_wins, baseline_losses], [recent_wins, recent_losses]]
    try:
        _, p_value, _, _ = stats.chi2_contingency(contingency)
    except ValueError:
        return None

    return {
        "baseline_win_rate": round(baseline_wins / len(baseline_outcomes), 4),
        "recent_win_rate": round(recent_wins / len(recent_outcomes), 4),
        "p_value": round(float(p_value), 6),
        "drift_detected": bool(p_value < SIGNIFICANCE_LEVEL),
        "baseline_sample_size": len(baseline_outcomes),
        "recent_sample_size": len(recent_outcomes),
    }
