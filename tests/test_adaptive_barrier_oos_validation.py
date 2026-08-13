"""Adaptive Barrier Engine — OOS doğrulama testleri (Faz 268-sonrası).
Tamamen sentetik, deterministik trade'lerle run_oos_validation()'ın
mantığını (train/test/embargo bölünmesi, path-relabeling ile karşı-olgusal
sonuç, baseline'a karşı gerçek karşılaştırma) doğrular — gerçek/canlı
backtest verisi burada YOK (bkz. scripts/ altındaki ayrı, canlı Binance
verisiyle çalışan analiz)."""
from analytics.adaptive_barrier_oos_validation import run_oos_validation


def _trade(entry_time, mae_pct, mfe_pct, net_return_pct, time_to_mae=100.0, time_to_mfe=50.0,
           direction="LONG", regime="bull", volatility_regime="normal", confidence=0.7) -> dict:
    return {
        "entry_time": entry_time,
        "mae_pct": mae_pct, "mfe_pct": mfe_pct,
        "time_to_mae_seconds": time_to_mae, "time_to_mfe_seconds": time_to_mfe,
        "direction": direction, "regime": regime,
        "volatility_regime": volatility_regime, "confidence": confidence,
        "net_return_pct": net_return_pct,
    }


def test_returns_insufficient_data_when_too_few_trades():
    trades = [_trade(i, -0.01, 0.03, -0.01) for i in range(10)]
    result = run_oos_validation(trades)
    assert result["status"] == "insufficient_data"


def test_oos_validation_compares_adaptive_barrier_against_real_baseline_on_held_out_trades():
    """70 TRAIN (tek profil: mae=-0.01/mfe=0.03 -> en iyi bariyer sl=0.01/
    tp=0.03 olarak bulunmalı) + 10 embargo (atlanır) + 30 TEST (15'i YENİ
    bariyerle take_profit'e, 15'i stop_loss'a giden farklı bir mae/mfe
    profili) — TEST'teki GERÇEK (baseline) sonuç kasıtlı olarak kötü
    (ortalama -0.005), adaptive'in path-relabeling ile türetilen sonucu
    bundan gerçekten daha iyi çıkmalı."""
    trades = []
    # TRAIN: 70 trade, tek profil.
    for i in range(70):
        trades.append(_trade(i, mae_pct=-0.01, mfe_pct=0.03, net_return_pct=0.0))
    # Embargo: 10 trade (train/test arasında atlanır, hangi profilde olduğu önemsiz).
    for i in range(70, 80):
        trades.append(_trade(i, mae_pct=-0.01, mfe_pct=0.03, net_return_pct=0.0))
    # TEST: 15 trade sl=0.01/tp=0.03 bariyeriyle SADECE TP'ye ulaşıyor.
    for i in range(80, 95):
        trades.append(_trade(
            i, mae_pct=-0.008, mfe_pct=0.03, time_to_mae=100.0, time_to_mfe=50.0,
            net_return_pct=-0.01 if i % 2 == 0 else 0.0,  # gerçekte kötü/nötr sonuçlanmış
        ))
    # TEST: 15 trade aynı bariyerle SADECE SL'e ulaşıyor.
    for i in range(95, 110):
        trades.append(_trade(
            i, mae_pct=-0.012, mfe_pct=0.002, time_to_mae=30.0, time_to_mfe=90.0,
            net_return_pct=-0.01 if i % 2 == 0 else 0.0,
        ))

    result = run_oos_validation(trades, train_fraction=70 / 110, embargo_count=10)

    assert result["status"] == "ok"
    assert result["train_count"] == 70
    assert result["test_count"] == 30
    assert result["matched_test_trades"] == 30
    # 15 take_profit (0.03-fees) + 15 stop_loss (-0.01-fees) -> pozitif ama karışık EV.
    assert result["adaptive_ev_pct"] > 0
    # Baseline (gerçek sonuç) kasıtlı olarak kötü -> adaptive gerçekten daha iyi.
    assert result["improvement_pct"] > 0
    assert result["adaptive_win_rate"] > result["baseline_win_rate"]
    assert result["dsr_adaptive"] is not None
    assert result["dsr_adaptive"]["sample_size"] == 30


def test_returns_no_barrier_groups_when_train_never_clears_min_group_size():
    """20 TRAIN trade AMA 4 farklı yön/rejim kombinasyonuna dağılmış —
    hiçbiri min_group_size=20'yi tek başına geçemiyor, tablo boş dönmeli."""
    trades = []
    regimes = ["bull", "bear", "range", "insufficient_data"]
    for i in range(20):
        trades.append(_trade(i, -0.01, 0.03, 0.0, regime=regimes[i % 4]))
    for i in range(20, 30):  # embargo + test dolgusu
        trades.append(_trade(i, -0.01, 0.03, 0.0, regime=regimes[i % 4]))
    for i in range(30, 55):
        trades.append(_trade(i, -0.01, 0.03, 0.0, regime=regimes[i % 4]))

    result = run_oos_validation(trades, train_fraction=20 / 55, embargo_count=10)
    assert result["status"] == "no_barrier_groups_cleared_threshold"


def test_returns_insufficient_matched_test_trades_when_test_bucket_never_seen_in_train():
    """TRAIN sadece LONG/bull, TEST sadece SHORT/bear -> recommend_barrier
    hiçbir test trade'i için eşleşme bulamaz, matched=0."""
    trades = []
    for i in range(70):
        trades.append(_trade(i, -0.01, 0.03, 0.0, direction="LONG", regime="bull"))
    for i in range(70, 80):
        trades.append(_trade(i, -0.01, 0.03, 0.0, direction="LONG", regime="bull"))
    for i in range(80, 110):
        trades.append(_trade(i, -0.01, 0.03, 0.0, direction="SHORT", regime="bear"))

    result = run_oos_validation(trades, train_fraction=70 / 110, embargo_count=10)
    assert result["status"] == "insufficient_matched_test_trades"
    assert result["matched_test_trades"] == 0
