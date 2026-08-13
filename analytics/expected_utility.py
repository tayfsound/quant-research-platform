"""Expected Utility ve Karar Teorisi — Faz 619-643 (Cognitive Core 2.0).

analytics/mae_mfe.py::compute_optimal_barrier() SADECE beklenen değeri
(EV) maksimize ediyor — riski (getiri VARYANSINI) hiç hesaba katmıyor.
İki aday bariyer çifti aynı EV'ye sahip olsa bile, biri çok daha yüksek
varyansla (bazen büyük kazanç, bazen büyük kayıp) gelebilir; standart
karar teorisi (von Neumann-Morgenstern beklenen fayda, CRRA — Constant
Relative Risk Aversion) bu ikisini AYNI şekilde değerlendirmez.

compute_crra_utility(): risk-aversion parametresi γ (gamma) ile bir
getiri dağılımının beklenen faydasını hesaplıyor. γ=0 saf EV
maksimizasyonu (risk-nötr) ile BİREBİR aynı sonucu verir, γ arttıkça
değişkenlik daha ağır cezalandırılır — γ=1 Kelly'nin (log-utility)
kendisi (services/kelly_sizing.py'nin dayandığı AYNI ilke, ama burada
tam CRRA ailesi parametrize edilebilir). İcat edilmiş bir formül değil,
standart Merton portfolio problem'inin risk-aversion parametrizasyonu.

Kasıtlı olarak SADECE ölçüm/karşılaştırma aracı — hiçbir pozisyon
büyüklüğü/bariyer kararını burada otomatik değiştirmiyor."""
import numpy as np

MIN_SAMPLE_SIZE = 10


def compute_crra_utility(returns: list[float], gamma: float = 1.0) -> dict | None:
    """returns: GERÇEK getiri gözlemleri (ondalık — 0.02 = %2, -0.01 = %1
    kayıp). gamma: risk-aversion (0=risk-nötr/EV, arttıkça risk-kaçınan).
    <MIN_SAMPLE_SIZE gözlemle fail-closed None. Bir gözlemde sermayenin
    tamamı ya da fazlası kaybedilmişse (wealth_relative<=0, return<=-1)
    CRRA/log-utility tanımsız olur — icat edilmiş bir değer üretmek yerine
    dürüstçe None döner."""
    if len(returns) < MIN_SAMPLE_SIZE:
        return None

    wealth_relatives = np.array([1.0 + r for r in returns])
    if np.any(wealth_relatives <= 0):
        return None

    if gamma == 1.0:
        utilities = np.log(wealth_relatives)
    else:
        utilities = (wealth_relatives ** (1 - gamma) - 1) / (1 - gamma)

    expected_utility = float(np.mean(utilities))
    if gamma == 1.0:
        certainty_equivalent_wealth = float(np.exp(expected_utility))
    else:
        base = expected_utility * (1 - gamma) + 1
        if base <= 0:
            return None
        certainty_equivalent_wealth = float(base ** (1 / (1 - gamma)))

    return {
        "expected_utility": round(expected_utility, 8),
        "certainty_equivalent_return": round(certainty_equivalent_wealth - 1.0, 6),
        "gamma": gamma,
        "sample_size": len(returns),
    }
