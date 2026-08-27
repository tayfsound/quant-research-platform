"""services/market_world_model_gatherer.py — Faz 366-devam. Kullanıcı
onayı: "gerçek margin bazlı pnl kullanarak düzeltmek daha sağlam olur."
Gerçek olay: pnl/margin denemesi TEK BAŞINA yetersizdi (basis_arb_v1
izolasyonu eksikti + 50 işlemi ardışık compound etmek her seferinde
TÜM bakiyenin yeniden kaldıraçla yatırıldığını varsayıyordu) — doğru
payda starting_capital (backtest/red_team.py'nin AYNI "sabit taban
sermaye" ilkesi).

Paylaşılan quantdb_test'te BAŞKA testlerin bıraktığı aşırı-capital
fikstürleri (bilerek $M'larca pnl'li, capital-limit gate testleri için)
gerçek DB'ye yazıp gather_market_world_model()'i uçtan uca çağırmayı
güvenilmez kılıyor (bkz. proje hafızası: shared test state bloat) — bu
yüzden burada DecisionPersistor.list_closed_trades ve AppSettingsRepository
monkeypatch'lenip mantık izole test ediliyor."""
from services.asset_class_performance_gatherer import (
    BASIS_ARB_EXPERIMENT_BUCKET,
    MULTI_TIMEFRAME_CASCADE_PREFIX,
)
from services.market_world_model_gatherer import gather_market_world_model


_counter = [0]


def _trade(pnl: float, experiment_bucket: str | None = None):
    _counter[0] += 1
    return {"pnl": pnl, "experiment_bucket": experiment_bucket, "closed_at": _counter[0], "opened_at": _counter[0]}


def test_returns_are_scaled_by_starting_capital_not_per_trade_margin(monkeypatch):
    """Kullanıcı bulgusu: pnl/margin ile 50 işlemi compound etmek
    trilyonlarca yüzdelik anlamsız değerler üretiyordu — doğru payda
    starting_capital, tipik bir işlemin etkisi ondalık yüzdeler
    mertebesinde olmalı."""
    starting_capital = 50_000.0
    # Marjine göre devasa (+%18600, leverage=5x, margin=$100 varsayımıyla)
    # ama sermayeye göre küçük bir kâr — pnl/margin kullanılsaydı TEK
    # BAŞINA patlardı.
    trades = [_trade(pnl=starting_capital * 0.0001) for _ in range(30)]

    monkeypatch.setattr(
        "database.repositories.app_settings_repository.AppSettingsRepository.get",
        lambda self, key: str(starting_capital),
    )
    monkeypatch.setattr(
        "database.repositories.decision_persistor.DecisionPersistor.list_closed_trades",
        lambda self, limit, exclude_experiment_bucket: trades,
    )

    result = gather_market_world_model()
    assert result["n_returns"] == 30
    paths = result["paths"]
    assert paths is not None
    # Gerçek starting_capital büyüklüğünde bir sermayede küçük, tekrarlı
    # kazançlar kümülatif getiriyi trilyonlarca büyütemez.
    assert abs(paths["mean_cumulative_return"]) < 10.0
    assert abs(paths["worst_cumulative_return"]) < 10.0


def test_basis_arb_v1_trades_are_excluded(monkeypatch):
    """Kullanıcı bulgusu: basis_arb_v1 (Faz 364'te kaldırıldı, backlog
    #30'da bilinen likidasyon-gecikmesi hataları var) council'in getiri
    dağılımını kirletmemeli."""
    starting_capital = 50_000.0
    trades = [_trade(pnl=0.01) for _ in range(30)] + [
        _trade(pnl=-999_999.0, experiment_bucket=BASIS_ARB_EXPERIMENT_BUCKET)
    ]

    monkeypatch.setattr(
        "database.repositories.app_settings_repository.AppSettingsRepository.get",
        lambda self, key: str(starting_capital),
    )
    monkeypatch.setattr(
        "database.repositories.decision_persistor.DecisionPersistor.list_closed_trades",
        lambda self, limit, exclude_experiment_bucket: trades,
    )

    result = gather_market_world_model()
    # basis_arb_v1 satırı hariç tutulduğu için sadece 30 (küçük, sağlıklı)
    # işlem kalmalı — 31 değil.
    assert result["n_returns"] == 30


def test_multi_timeframe_cascade_v1_trades_are_excluded(monkeypatch):
    """Kullanıcı bulgusu (2026-08-27): multi_timeframe_cascade_v1 (A/B
    deneyi, hem control hem treatment) 23 Ağustos'ta -$90,428 kaybetti —
    council'in gerçek getiri dağılımıyla ilgisi yok, aynı basis_arb_v1
    gerekçesiyle hariç tutulmalı."""
    starting_capital = 50_000.0
    trades = (
        [_trade(pnl=0.01) for _ in range(30)]
        + [_trade(pnl=-999_999.0, experiment_bucket=f"{MULTI_TIMEFRAME_CASCADE_PREFIX}:control")]
        + [_trade(pnl=-999_999.0, experiment_bucket=f"{MULTI_TIMEFRAME_CASCADE_PREFIX}:treatment")]
    )

    monkeypatch.setattr(
        "database.repositories.app_settings_repository.AppSettingsRepository.get",
        lambda self, key: str(starting_capital),
    )
    monkeypatch.setattr(
        "database.repositories.decision_persistor.DecisionPersistor.list_closed_trades",
        lambda self, limit, exclude_experiment_bucket: trades,
    )

    result = gather_market_world_model()
    assert result["n_returns"] == 30
