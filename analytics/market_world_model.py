"""Market World Model — Faz 901-940 (Cognitive Core 5.0-6.0).

risk/predictive/monte_carlo.py GERÇEK geçmiş getirilerden bootstrap
örnekleme yapıyor ama TEKİL (iid) noktaları yeniden örnekliyor — bu,
getiriler arasındaki GERÇEK ardışık bağımlılığı (volatilite kümelenmesi,
momentum/mean-reversion otokorelasyonu) YOK EDİYOR, her nokta bağımsızmış
gibi karıştırıyor. Bu modül, standart, literatürde tanımlı bir teknik
olan Moving Block Bootstrap'i (Künsch, 1989) ekliyor — TEKİL noktalar
yerine ARDIŞIK BLOKLAR yeniden örnekleniyor, gerçek zaman-serisi
bağımlılık yapısı büyük ölçüde korunuyor. İcat edilmiş bir simülasyon
değil.

Kasıtlı olarak SADECE simülasyon/rapor — hiçbir pozisyon/risk kararını
burada otomatik değiştirmiyor."""
import numpy as np

DEFAULT_N_PATHS = 1000

# Faz 369-devam — GPT dış rapor önerisi (kullanıcı isteği, iş sırasının
# 2. maddesi): "En kritik eksik drawdown + loss streak + CVaR ve block-size
# sensitivity testi." block = 5/10/20/30 GPT'nin kendi önerdiği varsayılan
# tarama seti.
DEFAULT_SENSITIVITY_BLOCK_SIZES = (5, 10, 20, 30)


def _path_max_drawdown(path_returns: list[float]) -> float:
    """TEK bir simüle edilmiş yolun (ardışık getiri dizisi) en derin
    tepe-den-dibe (peak-to-trough) düşüşü. Equity eğrisi 1.0'dan başlayıp
    her adımda (1+r) ile bileşiklenir; drawdown = (bugünkü_equity -
    o_ana_kadarki_zirve) / zirve — her zaman <=0. Boş dizide 0.0 (düşüş
    yok, çünkü hareket yok)."""
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in path_returns:
        equity *= (1.0 + r)
        peak = max(peak, equity)
        drawdown = (equity - peak) / peak if peak > 0 else 0.0
        max_dd = min(max_dd, drawdown)
    return max_dd


def _path_longest_loss_streak(path_returns: list[float]) -> int:
    """TEK bir simüle edilmiş yolda en uzun ardışık NEGATİF getiri
    serisinin uzunluğu — GPT'nin örneği: aynı p5'e sahip iki yol
    operasyonel olarak farklı risk taşıyabilir (kayıplar dağınık mı,
    yoksa uzun bir seride mi kümelenmiş)."""
    longest = 0
    current = 0
    for r in path_returns:
        if r < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def compute_block_bootstrap_paths(
    returns: list[float],
    block_size: int,
    path_length: int,
    n_paths: int = DEFAULT_N_PATHS,
    random_seed: int = 42,
) -> dict | None:
    """returns: GERÇEK kronolojik getiri serisi. block_size: yeniden
    örneklenen ardışık blok uzunluğu (>=1). path_length: üretilecek her
    yolun kaç dönem olacağı. <block_size*2 gözlemle ya da geçersiz
    parametrelerle fail-closed None döner — icat edilmiş bir simülasyon
    sonucu asla üretilmez. random_seed: tekrarlanabilirlik için sabit.

    Faz 369-devam — GPT dış rapor önerisi: "Şu an sadece cumulative return
    görüyorsunuz... maximum drawdown, en uzun kayıp serisi, %1 quantile,
    ve CVaR/Expected Shortfall eklerdim." p5/p95/worst/mean'in yanına:
    p1_cumulative_return, cvar_5_cumulative_return (en kötü %5'in
    ortalaması — TEK bir kuyruk noktası değil, kuyruğun KENDİSİ), ve HER
    yolun kendi equity eğrisinden hesaplanan max_drawdown/loss_streak
    dağılımlarının ortalaması+en kötüsü eklendi."""
    if block_size < 1 or path_length < 1 or len(returns) < block_size * 2:
        return None

    arr = np.array(returns, dtype=float)
    n = len(arr)
    n_blocks_available = n - block_size + 1
    if n_blocks_available < 1:
        return None

    rng = np.random.default_rng(random_seed)
    n_blocks_needed = int(np.ceil(path_length / block_size))

    cumulative_returns = np.empty(n_paths)
    max_drawdowns = np.empty(n_paths)
    loss_streaks = np.empty(n_paths, dtype=int)
    for i in range(n_paths):
        path: list[float] = []
        for _ in range(n_blocks_needed):
            start = int(rng.integers(0, n_blocks_available))
            path.extend(arr[start:start + block_size])
        path = path[:path_length]
        compounded = 1.0
        for r in path:
            compounded *= (1.0 + r)
        cumulative_returns[i] = compounded - 1.0
        max_drawdowns[i] = _path_max_drawdown(path)
        loss_streaks[i] = _path_longest_loss_streak(path)

    p5 = float(np.quantile(cumulative_returns, 0.05))
    # CVaR/Expected Shortfall: p5 SINIRINDAKİ tek noktayı değil, o
    # sınırın ALTINDA KALAN TÜM yolların ortalamasını raporluyor — "en
    # kötü %5 gerçekleşirse ortalama kayıp ne kadar" sorusuna cevap.
    tail = cumulative_returns[cumulative_returns <= p5]
    cvar_5 = float(tail.mean()) if len(tail) > 0 else p5

    return {
        "mean_cumulative_return": round(float(cumulative_returns.mean()), 6),
        "p1_cumulative_return": round(float(np.quantile(cumulative_returns, 0.01)), 6),
        "p5_cumulative_return": round(p5, 6),
        "p95_cumulative_return": round(float(np.quantile(cumulative_returns, 0.95)), 6),
        "worst_cumulative_return": round(float(cumulative_returns.min()), 6),
        "cvar_5_cumulative_return": round(cvar_5, 6),
        "mean_max_drawdown": round(float(max_drawdowns.mean()), 6),
        "worst_max_drawdown": round(float(max_drawdowns.min()), 6),
        "mean_loss_streak": round(float(loss_streaks.mean()), 2),
        "worst_loss_streak": int(loss_streaks.max()),
        "n_paths": n_paths,
        "block_size": block_size,
        "path_length": path_length,
    }


def compute_block_size_sensitivity(
    returns: list[float],
    path_length: int,
    n_paths: int = DEFAULT_N_PATHS,
    block_sizes: tuple[int, ...] = DEFAULT_SENSITIVITY_BLOCK_SIZES,
    random_seed: int = 42,
) -> dict | None:
    """Faz 369-devam — GPT dış rapor önerisi: "Block size = 10 seçimi
    sonuç üzerinde ciddi etki yaratabilir... block=5/10/20/30 ile ayrı
    ayrı simülasyon yapıp p5/worst/max_drawdown/loss_streak karşılaştırmak
    isterim. Stabil kalıyorsa güven artar, patlıyorsa risk ölçümünün
    kendisi block-size'a duyarlı demektir."

    AYNI returns dizisini SADECE block_size'ı değiştirerek defalarca
    compute_block_bootstrap_paths'e besler (icat edilmiş bir ikinci
    istatistik değil — mevcut fonksiyonun kendisiyle bir duyarlılık
    taraması). Veri yetersizliği yüzünden bazı block_size'lar None
    dönebilir (fail-closed, atlanır); İKİDEN AZ başarılı sonuçla
    duyarlılık değerlendirilemez (is_stable=None — "bilinmiyor", icat
    edilmiş bir "evet/hayır" asla üretilmez).

    is_stable eşiği: en kötü/en iyi p5'in mutlak değer oranı > 2.0 ise
    "duyarlı" sayılıyor — GPT'nin kendi örneklerinden türetildi (stabil
    örneği ~%17 göreceli fark, patlayan örneği ~21x fark; 2x aradaki net
    bir ayrım noktası, keyfi seçilmiş bir hassasiyet DEĞİL ama kesin bir
    bilimsel eşik de değil — bu YÜZDEN ham by_block_size verisi de HER
    ZAMAN tam olarak dönüyor, kullanıcı kendi eşiğini de görebilir)."""
    by_block_size: dict[int, dict] = {}
    for block_size in block_sizes:
        result = compute_block_bootstrap_paths(
            returns, block_size=block_size, path_length=path_length,
            n_paths=n_paths, random_seed=random_seed,
        )
        if result is not None:
            by_block_size[block_size] = result

    if len(by_block_size) < 2:
        return {"by_block_size": by_block_size, "is_stable": None, "p5_sensitivity_ratio": None}

    p5_values = [abs(r["p5_cumulative_return"]) for r in by_block_size.values()]
    smallest = min(p5_values)
    largest = max(p5_values)
    ratio = round(largest / smallest, 2) if smallest > 1e-12 else None

    return {
        "by_block_size": by_block_size,
        "is_stable": (ratio is not None and ratio <= 2.0),
        "p5_sensitivity_ratio": ratio,
    }
