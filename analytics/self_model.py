"""Self-Model — Faz 769-800 (Cognitive Core 3.0).

"Self-model" burada gerçek bir bilinç/öz-farkındalık iddiası DEĞİL —
sistemin KENDİ güvenilirliği hakkında halihazırda AYRI AYRI hesaplanan
sinyalleri (kalibrasyon — analytics/calibration_uncertainty.py, Sharpe
güvenilirliği — analytics/backtest_validation.py, kill switch durumu —
engines/risk_engine.py, feature/concept drift — analytics/model_drift.py
ve analytics/concept_drift.py) TEK bir tutarlı "öz-değerlendirme" anlık
görüntüsünde birleştiren bir içgözlem (introspection) katmanı. Sistem
"şu an kendi kararlarına ne kadar güvenmeli" sorusuna, HERHANGİ bir tek
sinyale değil, GERÇEKTEN hesaplanmış birden fazla bağımsız göstergenin
birleşimine dayanarak cevap verebiliyor.

Kasıtlı olarak SADECE rapor — hiçbir karar/risk parametresini burada
otomatik değiştirmiyor, hiçbir alt sinyali YENİDEN hesaplamıyor (her
girdi başka bir modülün GERÇEK çıktısı)."""

POOR_CALIBRATION_ECE_THRESHOLD = 0.1
UNTRUSTWORTHY_DSR_THRESHOLD = 0.3
DEGRADED_DSR_THRESHOLD = 0.5


def compute_self_reliability_snapshot(
    ece: float | None,
    recent_dsr: float | None,
    kill_switch_active: bool,
    known_feature_drift_count: int,
    concept_drift_detected: bool,
) -> dict:
    """Her girdi GERÇEKTEN başka bir modülün ürettiği bir sonuç — burada
    yeniden hesaplanmıyor, sadece BİRLEŞTİRİLİYOR. overall_reliability:
    'high'/'degraded'/'untrustworthy' — sabit, açık kurallara dayalı bir
    sınıflandırma, icat edilmiş bir skor değil."""
    flags: list[str] = []
    if kill_switch_active:
        flags.append("kill_switch_active")
    if ece is not None and ece > POOR_CALIBRATION_ECE_THRESHOLD:
        flags.append("poor_calibration")
    if recent_dsr is not None and recent_dsr < DEGRADED_DSR_THRESHOLD:
        flags.append("sharpe_likely_noise")
    if known_feature_drift_count > 0:
        flags.append(f"{known_feature_drift_count}_features_drifted")
    if concept_drift_detected:
        flags.append("concept_drift_detected")

    if kill_switch_active or (recent_dsr is not None and recent_dsr < UNTRUSTWORTHY_DSR_THRESHOLD):
        overall = "untrustworthy"
    elif flags:
        overall = "degraded"
    else:
        overall = "high"

    return {
        "overall_reliability": overall,
        "reliability_flags": flags,
        "inputs": {
            "ece": ece,
            "recent_dsr": recent_dsr,
            "kill_switch_active": kill_switch_active,
            "known_feature_drift_count": known_feature_drift_count,
            "concept_drift_detected": concept_drift_detected,
        },
    }
