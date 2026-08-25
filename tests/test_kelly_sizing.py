"""Faz 268g — "İsabeti artırmanın yolu daha akıllı kullanım" yol
haritasının D fazı (Signal-Strength Position Sizing). Gerçek bulgu:
MetaStage'in ACT dalı confidence=0.71 ile 0.99'u AYNI (tam) büyüklükte
açıyordu — REDUCE dalı zaten confidence'a orantılı küçülüyordu, ama
ACT-tier İÇİNDE hiç ayrım yoktu."""
from datetime import UTC, datetime
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.kelly_sizing import kelly_fraction, kelly_size_multiplier


def test_kelly_fraction_matches_hand_computed_value():
    # f* = p - q/b, b = avg_win/avg_loss
    # p=0.6, avg_win=10, avg_loss=5 -> b=2, q=0.4 -> f = 0.6 - 0.2 = 0.4
    result = kelly_fraction(win_rate=0.6, avg_win=10.0, avg_loss=5.0)
    assert abs(result - 0.4) < 1e-9


def test_kelly_fraction_negative_edge_clamps_to_zero():
    """Kayıp beklentisi (negatif Kelly) 0'a kırpılmalı — "bahis yapma"
    fail-closed, asla negatif/icat edilmiş bir büyüklük değil."""
    result = kelly_fraction(win_rate=0.2, avg_win=1.0, avg_loss=5.0)
    assert result == 0.0


def test_kelly_fraction_with_no_win_or_loss_data_returns_zero():
    assert kelly_fraction(win_rate=0.5, avg_win=0.0, avg_loss=5.0) == 0.0
    assert kelly_fraction(win_rate=0.5, avg_win=5.0, avg_loss=0.0) == 0.0


def test_kelly_fraction_result_never_exceeds_one():
    result = kelly_fraction(win_rate=0.95, avg_win=100.0, avg_loss=1.0)
    assert result <= 1.0


def test_kelly_size_multiplier_with_no_data_defaults_to_full_size(monkeypatch):
    """Faz 268g — yeterli veri olmayan bir kova için (fail-closed) çarpan
    1.0 — mevcut (tam boyut) davranış hiç değişmeden korunur."""
    from services import kelly_sizing

    monkeypatch.setattr(kelly_sizing, "get_confidence_bucket_payoff_stats", lambda: {})
    assert kelly_size_multiplier(0.8) == 1.0


def test_kelly_size_multiplier_is_half_of_kelly_fraction_and_never_exceeds_one(monkeypatch):
    from services import kelly_sizing

    monkeypatch.setattr(
        kelly_sizing,
        "get_confidence_bucket_payoff_stats",
        lambda: {0.8: {"win_rate": 0.6, "avg_win": 10.0, "avg_loss": 5.0, "sample_count": 50}},
    )
    # f* = 0.4 (yukarıdaki testle aynı), half-Kelly = 0.2
    result = kelly_size_multiplier(0.8)
    assert abs(result - 0.2) < 1e-9
    assert result <= 1.0


def test_kelly_size_multiplier_rounds_confidence_to_nearest_bucket(monkeypatch):
    from services import kelly_sizing

    monkeypatch.setattr(
        kelly_sizing,
        "get_confidence_bucket_payoff_stats",
        lambda: {0.8: {"win_rate": 0.6, "avg_win": 10.0, "avg_loss": 5.0, "sample_count": 50}},
    )
    # 0.77 -> 0.8 kovasına yuvarlanır (aynı kova/eğri deseni, confidence_calibration.py ile tutarlı)
    result = kelly_size_multiplier(0.77)
    assert abs(result - 0.2) < 1e-9


# Faz 290 — EV kapısının rejime koşullandırılması (dış rapor doğrulaması,
# 2026-08-19): Kelly boyutlandırma önceden SADECE confidence kovasına
# bakıyordu.

def test_kelly_size_multiplier_prefers_regime_specific_stats_when_available(monkeypatch):
    from services import kelly_sizing

    # confidence-only kova iyimser (f*=0.4, half-Kelly=0.2) ama bu rejimde
    # aynı confidence kovasının GERÇEK dağılımı çok daha kötü (f*=0) —
    # rejim-özel veri varsa o kullanılmalı, global kova değil.
    monkeypatch.setattr(
        kelly_sizing, "get_confidence_bucket_payoff_stats",
        lambda: {0.8: {"win_rate": 0.6, "avg_win": 10.0, "avg_loss": 5.0, "sample_count": 50}},
    )
    monkeypatch.setattr(
        kelly_sizing, "get_regime_confidence_bucket_payoff_stats",
        lambda: {("bearish_high", 0.8): {"win_rate": 0.2, "avg_win": 1.0, "avg_loss": 5.0, "sample_count": 30}},
    )
    result = kelly_size_multiplier(0.8, regime="bearish_high")
    assert result == 0.0  # negatif kenar, fail-closed sıfır


def test_kelly_size_multiplier_falls_back_to_global_bucket_when_regime_data_insufficient(monkeypatch):
    from services import kelly_sizing

    monkeypatch.setattr(
        kelly_sizing, "get_confidence_bucket_payoff_stats",
        lambda: {0.8: {"win_rate": 0.6, "avg_win": 10.0, "avg_loss": 5.0, "sample_count": 50}},
    )
    # bu rejim için hiç veri yok -> global kovaya (half-Kelly=0.2) düşmeli
    monkeypatch.setattr(kelly_sizing, "get_regime_confidence_bucket_payoff_stats", lambda: {})
    result = kelly_size_multiplier(0.8, regime="bearish_high")
    assert abs(result - 0.2) < 1e-9


def test_kelly_size_multiplier_without_regime_argument_uses_confidence_only_path(monkeypatch):
    from services import kelly_sizing

    monkeypatch.setattr(
        kelly_sizing, "get_confidence_bucket_payoff_stats",
        lambda: {0.8: {"win_rate": 0.6, "avg_win": 10.0, "avg_loss": 5.0, "sample_count": 50}},
    )
    result = kelly_size_multiplier(0.8)  # regime=None (varsayılan) — mevcut davranış
    assert abs(result - 0.2) < 1e-9


def test_compute_regime_confidence_bucket_payoff_stats_reflects_real_closed_trades():
    """Gerçek DB'ye karşı: bir (rejim, confidence) kovasına yeterli (>=50,
    Faz 363'te 20'den çıkarıldı) gerçek kapanmış işlem eklenince, GERÇEK
    verilerden doğru hesaplanmalı — ve market_regime=NULL olan kapanışlar
    bu kovaya hiç karışmamalı."""
    from services.kelly_sizing import compute_regime_confidence_bucket_payoff_stats

    symbol = f"KELLYREGIME{uuid4().hex[:6]}"
    regime = f"bullish_high_{uuid4().hex[:6]}"  # başka testlerle çakışmasın diye benzersiz
    pnls = [10.0] * 36 + [-5.0] * 24

    now = datetime.now(UTC)
    for pnl in pnls:
        event = DecisionEvent(
            id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
            final_size=1.0, confidence=0.9, status="open", entry_price=100.0, quantity=1.0,
        )
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            repo.persist(event)
            repo.close_position(
                decision_id=str(event.id), exit_price=100.0, pnl=pnl, closed_at=now,
                market_regime=regime,
            )

    stats = compute_regime_confidence_bucket_payoff_stats()
    bucket = stats.get((regime, 0.9))
    assert bucket is not None
    assert bucket["sample_count"] == 60
    assert bucket["win_rate"] == 0.6
    assert bucket["avg_win"] == 10.0
    assert bucket["avg_loss"] == 5.0


def test_compute_confidence_bucket_payoff_stats_reflects_real_closed_trades():
    """Gerçek DB'ye karşı: bir kovaya (0.9) yeterli (>=20) gerçek kapanmış
    işlem eklenince, o kovanın win_rate/avg_win/avg_loss'u GERÇEK
    verilerden doğru hesaplanmalı."""
    from services.kelly_sizing import compute_confidence_bucket_payoff_stats

    symbol = f"KELLYTEST{uuid4().hex[:6]}"
    now_pnls = [10.0] * 15 + [-5.0] * 10  # 15 kazanç, 10 kayıp, 25 toplam (eşiği geçiyor)

    now = datetime.now(UTC)
    for pnl in now_pnls:
        event = DecisionEvent(
            id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
            final_size=1.0, confidence=0.9, status="open", entry_price=100.0, quantity=1.0,
        )
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            repo.persist(event)
            repo.close_position(decision_id=str(event.id), exit_price=100.0, pnl=pnl, closed_at=now)

    stats = compute_confidence_bucket_payoff_stats()
    bucket = stats.get(0.9)
    assert bucket is not None
    assert bucket["sample_count"] >= 25
    # Tam eşit oranları elle doğrulamak yerine (paylaşılan test DB'de
    # başka testlerden de 0.9 kovasına kayıt gelmiş olabilir), sadece
    # gerçekçi bir aralıkta olduklarını doğruluyoruz.
    assert 0.0 < bucket["win_rate"] < 1.0
    assert bucket["avg_win"] > 0
    assert bucket["avg_loss"] > 0
