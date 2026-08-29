"""Market World Model (Moving Block Bootstrap) testleri — Faz 901-940 (Cognitive Core 5.0-6.0)."""
from analytics.market_world_model import compute_block_bootstrap_paths, compute_block_size_sensitivity


def test_constant_returns_produce_the_exact_compounded_result():
    returns = [0.01] * 20
    result = compute_block_bootstrap_paths(returns, block_size=3, path_length=10, n_paths=50)
    assert result is not None
    expected = (1.01 ** 10) - 1.0
    assert abs(result["mean_cumulative_return"] - expected) < 1e-6
    assert abs(result["p5_cumulative_return"] - expected) < 1e-6
    assert abs(result["worst_cumulative_return"] - expected) < 1e-6
    # Faz 369-devam — hep pozitif, hep aynı getiri: equity monoton artıyor,
    # hiçbir düşüş (drawdown) ve hiçbir kayıp serisi (loss streak) olamaz.
    # cvar_5/p1 de mean/p5 ile BİREBİR aynı olmalı (tüm yollar deterministik
    # olarak özdeş).
    assert result["mean_max_drawdown"] == 0.0
    assert result["worst_max_drawdown"] == 0.0
    assert result["mean_loss_streak"] == 0.0
    assert result["worst_loss_streak"] == 0
    assert abs(result["p1_cumulative_return"] - expected) < 1e-6
    assert abs(result["cvar_5_cumulative_return"] - expected) < 1e-6


def test_constant_negative_returns_produce_full_drawdown_and_full_loss_streak():
    """Faz 369-devam — GPT önerisi: hep negatif getiri deterministik
    olarak equity'nin sürekli düşmesi (max_drawdown = compounded getirinin
    KENDİSİ, çünkü zirve hiç yenilenmiyor) ve TÜM path_length boyunca
    kesintisiz bir kayıp serisi (loss_streak = path_length) anlamına
    gelmeli."""
    returns = [-0.01] * 20
    result = compute_block_bootstrap_paths(returns, block_size=3, path_length=10, n_paths=50)
    assert result is not None
    expected = (0.99 ** 10) - 1.0
    assert abs(result["mean_max_drawdown"] - expected) < 1e-6
    assert abs(result["worst_max_drawdown"] - expected) < 1e-6
    assert result["mean_loss_streak"] == 10.0
    assert result["worst_loss_streak"] == 10


def test_cvar_is_at_least_as_bad_as_p5_and_p1_is_at_least_as_bad_as_p5():
    """CVaR (kuyruğun ortalaması) tanım gereği p5'ten (kuyruğun sınırı)
    daha iyi olamaz — VE p1 (daha dar/daha uç bir kesim) p5'ten daha
    kötü ya da eşit olmalı."""
    returns = [0.02, -0.03, 0.01, -0.01, 0.04, -0.02, 0.015, -0.005, 0.03, -0.01] * 3
    result = compute_block_bootstrap_paths(returns, block_size=4, path_length=20, n_paths=500)
    assert result["cvar_5_cumulative_return"] <= result["p5_cumulative_return"] + 1e-9
    assert result["p1_cumulative_return"] <= result["p5_cumulative_return"] + 1e-9
    assert result["worst_max_drawdown"] <= result["mean_max_drawdown"] + 1e-9
    assert result["worst_loss_streak"] >= result["mean_loss_streak"] - 1e-9


def test_same_seed_is_reproducible():
    returns = [0.01, -0.02, 0.03, -0.01, 0.02, 0.01, -0.015, 0.025, 0.01, -0.005] * 3
    result_a = compute_block_bootstrap_paths(returns, block_size=3, path_length=15, n_paths=200, random_seed=7)
    result_b = compute_block_bootstrap_paths(returns, block_size=3, path_length=15, n_paths=200, random_seed=7)
    assert result_a == result_b


def test_percentile_ordering_is_sane():
    returns = [0.02, -0.03, 0.01, -0.01, 0.04, -0.02, 0.015, -0.005, 0.03, -0.01] * 3
    result = compute_block_bootstrap_paths(returns, block_size=4, path_length=20, n_paths=500)
    assert result["p5_cumulative_return"] <= result["mean_cumulative_return"] <= result["p95_cumulative_return"]
    assert result["worst_cumulative_return"] <= result["p5_cumulative_return"]


def test_insufficient_data_is_fail_closed():
    returns = [0.01] * 4
    assert compute_block_bootstrap_paths(returns, block_size=3, path_length=10) is None


def test_invalid_block_size_or_path_length_is_fail_closed():
    returns = [0.01] * 20
    assert compute_block_bootstrap_paths(returns, block_size=0, path_length=10) is None
    assert compute_block_bootstrap_paths(returns, block_size=3, path_length=0) is None


def test_block_size_sensitivity_reports_stable_for_constant_returns():
    """Faz 369-devam — GPT önerisi: block=5/10/20/30 taraması. Sabit
    getiride block_size ne olursa olsun sonuç MATEMATİKSEL olarak
    özdeş (deterministik compounding) — is_stable=True, ratio=1.0
    olmalı, GPT'nin "stabil kalıyorsa güven artar" örneğinin en net hali."""
    returns = [0.01] * 100
    result = compute_block_size_sensitivity(returns, path_length=20, n_paths=50)
    assert result is not None
    assert set(result["by_block_size"].keys()) == {5, 10, 20, 30}
    assert result["is_stable"] is True
    assert result["p5_sensitivity_ratio"] == 1.0


def test_block_size_sensitivity_is_none_verdict_with_fewer_than_two_successful_sizes():
    """Faz 369-devam — fail-closed: veri sadece EN KÜÇÜK block_size'ı
    (5) destekleyecek kadarsa (len >= 5*2=10 ama < 10*2=20), duyarlılık
    DEĞERLENDİRİLEMEZ — icat edilmiş bir True/False asla üretilmez."""
    returns = [0.01] * 12
    result = compute_block_size_sensitivity(returns, path_length=8, n_paths=20)
    assert result is not None
    assert set(result["by_block_size"].keys()) == {5}
    assert result["is_stable"] is None
    assert result["p5_sensitivity_ratio"] is None


def test_block_size_sensitivity_flags_unstable_when_p5_diverges_across_block_sizes():
    """Kasıtlı olarak block_size'a göre GERÇEKTEN farklı davranan bir
    getiri serisi (ampirik doğrulandı): uzun sakin bir dönemin sonuna
    kısa ama SERT bir çöküş bloğu ekleniyor. Küçük block (5) çöküşü
    parçalayıp çoğu yolun içine az miktarda karıştırırken, büyük block
    (30) ya çöküşü hiç yakalamıyor ya da yakaladığında path_length'in
    tamamını kaplıyor — GPT'nin uyardığı TAM senaryo: risk ölçümünün
    kendisi block_size seçimine göre büyük ölçüde değişiyor (ratio>2)."""
    returns = [0.001, -0.0005] * 100 + [-0.08] * 6
    result = compute_block_size_sensitivity(returns, path_length=30, n_paths=500, block_sizes=(5, 30))
    assert result is not None
    assert result["p5_sensitivity_ratio"] is not None
    assert result["p5_sensitivity_ratio"] > 2.0
    assert result["is_stable"] is False
