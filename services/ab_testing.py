"""Faz 250: Live A/B Testing Framework.

Faz 233'te kaldırılan experiment_registry tablosunun (kullanıcı bulgusu:
"depolama sıkıntısı... hiçbir ajan/karar mekanizması bunu okumuyordu")
AKSİNE — bu modül bilinçli olarak write-only bir denetim kaydı değil,
gerçekten OKUNAN (evaluate_experiment) bir mekanizma. Yeni bir tablo da
açmıyor: decisions.experiment_bucket (Faz 250 migration'ı) zaten var olan,
sınırlı büyüyen bir tabloyu genişletiyor.

Welch's t-test (eşit varyans VARSAYILMADAN — iki kovanın örneklem
büyüklüğü/varyansı doğal olarak farklı olabilir, klasik Student t-test'in
varsayımı burada güvenli değil) iki kovanın gerçek pnl dağılımını
karşılaştırıyor."""
import random

_MIN_SAMPLES_PER_BUCKET = 30
_SIGNIFICANCE_LEVEL = 0.05


def assign_bucket(control_weight: float = 0.5) -> str:
    """Her çağrıda bağımsız, gerçekten rastgele bir kova ataması —
    sembole/zamana göre deterministik DEĞİL (paralel paper-trading
    kovalarının istatistiksel olarak karşılaştırılabilir olması için
    gerçek rastgele örnekleme gerekiyor, deterministik bir hash değil)."""
    return "control" if random.random() < control_weight else "treatment"


def welch_t_test(sample_a: list[float], sample_b: list[float]) -> dict:
    """İki bağımsız örneklemin ortalamalarını, eşit varyans varsaymadan
    karşılaştırır. Örneklemlerden biri çok küçükse (<2) fail-closed None
    döner — icat edilmiş bir p-value asla üretilmez."""
    if len(sample_a) < 2 or len(sample_b) < 2:
        return {"t_statistic": None, "p_value": None, "significant": None}

    from scipy import stats

    result = stats.ttest_ind(sample_a, sample_b, equal_var=False)
    p_value = float(result.pvalue)
    return {
        "t_statistic": float(result.statistic),
        "p_value": p_value,
        "significant": p_value < _SIGNIFICANCE_LEVEL,
    }


def evaluate_experiment(
    experiment_name: str, min_samples_per_bucket: int = _MIN_SAMPLES_PER_BUCKET,
) -> dict:
    """Gerçek kapanmış kararlardan (decisions.experiment_bucket LIKE
    '{experiment_name}:%') control/treatment kovalarının win_rate/avg_pnl'
    ini ve Welch's t-test sonucunu hesaplar. Fail-closed: yeterli örneklem
    yoksa (her iki kovada da >= min_samples_per_bucket) "insufficient_data"
    verdict'i döner, hiçbir promote/rollback önerisi yapılmaz."""
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        rows = session.execute(text("""
            SELECT experiment_bucket, pnl FROM decisions
            WHERE status = 'closed' AND excluded_from_stats = false
                AND experiment_bucket LIKE :pattern AND pnl IS NOT NULL
        """), {"pattern": f"{experiment_name}:%"}).fetchall()

    control_pnls = [float(pnl) for bucket, pnl in rows if bucket == f"{experiment_name}:control"]
    treatment_pnls = [float(pnl) for bucket, pnl in rows if bucket == f"{experiment_name}:treatment"]

    result = {
        "experiment_name": experiment_name,
        "control_sample_count": len(control_pnls),
        "treatment_sample_count": len(treatment_pnls),
    }

    if len(control_pnls) < min_samples_per_bucket or len(treatment_pnls) < min_samples_per_bucket:
        result["verdict"] = "insufficient_data"
        return result

    control_win_rate = sum(1 for p in control_pnls if p > 0) / len(control_pnls)
    treatment_win_rate = sum(1 for p in treatment_pnls if p > 0) / len(treatment_pnls)
    control_avg_pnl = sum(control_pnls) / len(control_pnls)
    treatment_avg_pnl = sum(treatment_pnls) / len(treatment_pnls)

    t_test = welch_t_test(treatment_pnls, control_pnls)

    result.update({
        "control_win_rate": control_win_rate,
        "treatment_win_rate": treatment_win_rate,
        "control_avg_pnl": control_avg_pnl,
        "treatment_avg_pnl": treatment_avg_pnl,
        "t_statistic": t_test["t_statistic"],
        "p_value": t_test["p_value"],
    })

    if not t_test["significant"]:
        result["verdict"] = "no_significant_difference"
    elif treatment_avg_pnl > control_avg_pnl:
        result["verdict"] = "promote_treatment"
    else:
        result["verdict"] = "rollback_treatment"

    return result
