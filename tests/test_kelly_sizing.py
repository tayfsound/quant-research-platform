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

def test_kelly_size_multiplier_never_drops_below_the_min_multiplier_floor(monkeypatch):
    """Faz 370-devam — KRİTİK canlı olay (2026-08-29, kullanıcı bulgusu):
    çarpan literal 0.0'a inebiliyordu — diğer TÜM sizing gate'lerin
    (self_correction/self_model/pivotal_agent/symbol_performance/mae_mfe_
    bucket) aksine, onlar hep bir MIN_MULTIPLIER tabanı kullanıyordu.
    Gerçek sonuç: negatif Sharpe döneminde bazı confidence kovaları 0.0'a
    düşünce sistem HİÇ yeni işlem açamadı — yeni işlem olmayınca "son N
    kapanmış" penceresi eski/kötü verilerle dolu kalmaya devam etti,
    kendi kendini besleyen bir kilitlenme döngüsü oluştu (5+ saat, sıfır
    açılış). Taban artık kelly_fraction NE KADAR negatif çıkarsa çıksın
    çarpanı asla 0.0'ın altına düşürmüyor — sistem her zaman KÜÇÜK bir
    boyutla yeni, temiz veri üretip döngüyü kırabiliyor."""
    from services import kelly_sizing

    # Çok kötü bir kova (win_rate düşük, kayıplar kazançlardan büyük) —
    # kelly_fraction kesinlikle 0.0 döner, ama kelly_size_multiplier
    # HÂLÂ MIN_MULTIPLIER'ı vermeli, literal 0.0 değil.
    monkeypatch.setattr(
        kelly_sizing, "get_confidence_bucket_payoff_stats",
        lambda: {0.5: {"win_rate": 0.1, "avg_win": 1.0, "avg_loss": 100.0, "sample_count": 500}},
    )
    result = kelly_size_multiplier(0.5)
    assert result == kelly_sizing.MIN_MULTIPLIER
    assert result > 0.0


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
    # Faz 370-devam — negatif kenar artık literal 0.0 DEĞİL, MIN_MULTIPLIER
    # (0.1) tabanına düşüyor — sistemin tamamen kilitlenip yeni veri
    # üretemez hale gelmesini önlemek için (bkz. kelly_sizing.py üstündeki
    # not, canlı kilitlenme olayı).
    assert result == kelly_sizing.MIN_MULTIPLIER


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


def test_compute_confidence_bucket_payoff_stats_excludes_pump_fade_and_basis_arb():
    """Faz 363 — kritik bulgu, gerçek veriyle doğrulandı: pump_fade_v1/
    basis_arb_v1 (AI konseyinden TAMAMEN izole, mekanik stratejiler)
    confidence alanını hiç doldurmuyor — round(confidence,1)=0.0 kovasına
    yığılıp (canlıda 199 kayıttan 197'si) o kovanın istatistiğini BÜYÜK
    ÖLÇÜDE (-$236.937'lik zararın -$236.830'u) pump_fade_v1'e ait yapıyordu.
    Bu test, dev boyutlu bir pump_fade_v1 zararının hiçbir kovaya HİÇ
    girmediğini (before/after karşılaştırmasıyla, paylaşılan DB state'ine
    bağımlı olmadan) kanıtlıyor."""
    from services.kelly_sizing import compute_confidence_bucket_payoff_stats

    symbol = f"KELLYPUMPFADE{uuid4().hex[:6]}"
    now = datetime.now(UTC)

    before = compute_confidence_bucket_payoff_stats()

    # Nadir kullanılan bir kova (0.15 -> round=0.1 veya 0.2 olabilir,
    # gerçek round() davranışına göre) yerine, mevcut bir kovayı (0.9)
    # DEV BOYUTLU bir zararla "kirletmeye çalışıyoruz" — eğer izolasyon
    # BOZULURSA bu, o kovanın avg_loss'unu göze çarpacak kadar bozardı.
    for _ in range(30):
        event = DecisionEvent(
            id=uuid4(), symbol=symbol, proposed_direction="SHORT", final_action="SHORT",
            final_size=1.0, confidence=0.9, status="open", entry_price=100.0, quantity=1.0,
            experiment_bucket="pump_fade_v1",
        )
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            repo.persist(event)
            repo.close_position(decision_id=str(event.id), exit_price=100.0, pnl=-50000.0, closed_at=now)

    after = compute_confidence_bucket_payoff_stats()

    before_bucket = before.get(0.9) or {"sample_count": 0, "avg_loss": 0.0}
    after_bucket = after.get(0.9)
    assert after_bucket is not None
    # Örneklem sayısı pump_fade_v1 eklemesinden HİÇ etkilenmemeli.
    assert after_bucket["sample_count"] == before_bucket["sample_count"]
    # avg_loss $50.000'lik pump_fade zararından etkilenseydi devasa
    # (onlarca bin $) çıkardı — makul bir üst sınırla bunun olmadığını
    # kanıtlıyoruz.
    assert after_bucket["avg_loss"] < 10000.0
