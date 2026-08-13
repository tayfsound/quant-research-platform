"""Backtest Bilimsel Doğrulama — Deflated Sharpe Ratio (DSR) — Faz 669-693
(Cognitive Core 2.0 / M7).

Bu proje boyunca çok sayıda strateji/parametre/ajan varyantı denendi
(backtest'ler, weight tuning, CMA-ES). Ham bir Sharpe oranı, KAÇ farklı
şeyin denendiğini hesaba katmaz — yeterince çok deneme yapılırsa, hiçbir
gerçek edge olmasa bile SADECE ŞANSLA yüksek bir Sharpe elde edilebilir
(multiple testing / selection bias). Deflated Sharpe Ratio (Bailey &
López de Prado, 2014), gözlemlenen Sharpe oranının, DENEME SAYISI ve
getiri dağılımının çarpıklık/basıklığı düzeltilmiş haliyle GERÇEKTEN
sıfırdan farklı (0 ile 1 arasında bir olasılık) olma olasılığını
hesaplıyor — icat edilmiş bir düzeltme değil, literatürde standart
kapalı-form bir formül (mlfinlab ve benzeri açık-kaynak uygulamalarda
kullanılan pratik varyant).

Kasıtlı olarak SADECE değerlendirme/rapor — hiçbir stratejiyi burada
otomatik onaylamıyor/reddetmiyor."""
import numpy as np
from scipy import stats

MIN_SAMPLE_SIZE = 20
_EULER_GAMMA = 0.5772156649015329


def compute_deflated_sharpe_ratio(returns: list[float], n_trials: int) -> dict | None:
    """returns: GERÇEK dönemsel getiri gözlemleri. n_trials: bu strateji
    seçilmeden ÖNCE GERÇEKTEN denenen (karşılaştırılan) strateji/parametre
    sayısı — dürüstçe raporlanmalı, küçük gösterilirse DSR yapay şekilde
    yüksek çıkar (bu fonksiyon n_trials'ı doğrulayamaz, çağıran tarafın
    sorumluluğu). <MIN_SAMPLE_SIZE gözlem, n_trials<1 ya da sabit
    (varyanssız) getiri serisiyle fail-closed None döner."""
    if len(returns) < MIN_SAMPLE_SIZE or n_trials < 1:
        return None

    arr = np.array(returns, dtype=float)
    n = len(arr)
    std = arr.std(ddof=1)
    if std == 0:
        return None

    sr_hat = float(arr.mean() / std)
    skew = float(stats.skew(arr))
    kurt = float(stats.kurtosis(arr, fisher=False))  # ham basıklık (normal dağılım=3)

    sr_hat_variance = (1 - skew * sr_hat + ((kurt - 1) / 4) * sr_hat ** 2) / (n - 1)
    if sr_hat_variance <= 0 or np.isnan(sr_hat_variance):
        return None
    sr_std = float(np.sqrt(sr_hat_variance))

    if n_trials <= 1:
        sr_0 = 0.0
    else:
        sr_0 = sr_std * (
            (1 - _EULER_GAMMA) * stats.norm.ppf(1 - 1.0 / n_trials)
            + _EULER_GAMMA * stats.norm.ppf(1 - 1.0 / (n_trials * np.e))
        )

    z = (sr_hat - sr_0) / sr_std
    dsr = float(stats.norm.cdf(z))

    return {
        "sharpe_ratio": round(sr_hat, 6),
        "expected_max_sharpe_under_null": round(sr_0, 6),
        "deflated_sharpe_ratio": round(dsr, 6),
        "n_trials": n_trials,
        "sample_size": n,
        "genuinely_skillful": bool(dsr > 0.95),
    }
