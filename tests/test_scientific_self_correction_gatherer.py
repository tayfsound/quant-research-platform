"""Faz 356 — services/scientific_self_correction_gatherer.py gerçek veri
entegrasyon testleri (analytics/scientific_self_correction.py'nin kendi
saf-fonksiyon testleri tests/test_scientific_self_correction.py'de zaten var)."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.scientific_self_correction_gatherer import gather_scientific_self_correction

_SYMBOL = "SSCTESTUSDT"


def _persist_closed_trade(direction: str, win: bool, closed_at: datetime, experiment_bucket: str | None = None) -> None:
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        event = DecisionEvent(
            id=uuid4(),
            symbol=_SYMBOL,
            proposed_direction=direction,
            final_action=direction,
            final_size=0.1,
            confidence=0.7,
            status="open",
            entry_price=100.0,
            quantity=1.0,
            opened_at=closed_at - timedelta(minutes=10),
            agent_opinions=[],
            market_snapshot={"features": {}},
            experiment_bucket=experiment_bucket,
        )
        persistor.persist(event)
        persistor.close_position(
            decision_id=str(event.id),
            exit_price=101.0 if win else 99.0,
            pnl=1.0 if win else -1.0,
            closed_at=closed_at,
            outcome={"win": win},
        )


def _cleanup() -> None:
    with SessionFactory.get_session() as session:
        from sqlalchemy import text
        session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": _SYMBOL})
        session.commit()


def test_gather_scientific_self_correction_flags_real_degradation():
    """Faz 482 — bu test eskiden GLOBAL `direction=LONG` segmentine
    bakıyordu ve TAM PAKET koşusunda düşüyordu: paylaşılan quantdb_test'te
    başka testlerin bıraktığı LONG kapanmış işlemler (gerçek ölçüm:
    original_n=81, recent_n=697) enjekte edilen bozulmayı seyreltip
    `significant_change`'i False yapıyordu. İlk denemem "mevcut segmente
    göre ölçekle" idi — ama o kurgu recent_n=697 için 7.600 satır ekleme
    gerektiriyordu ve DB büyüdükçe daha da kötüleşecekti.

    Doğru çözüm, gatherer'ın KENDİ segment şemasını kullanmak: segmentler
    `overall` / `direction=X` / `experiment_bucket=X` (bkz.
    scientific_self_correction_gatherer.py::_fetch_wins_and_totals).
    Benzersiz bir `experiment_bucket`, hiçbir başka testin dokunamayacağı
    TAMAMEN İZOLE bir segment veriyor — bozulma sinyali artık paylaşılan
    DB durumundan bağımsız."""
    now = datetime.now(UTC)
    old = now - timedelta(days=30)
    # pump_fade/basis_arb DIŞINDA bir kova: o ikisi kasıtlı olarak
    # dışlanıyor (bkz. _fetch_wins_and_totals docstring'i).
    bucket = f"ssc_degradation_{uuid4().hex[:8]}"

    try:
        for _ in range(23):
            _persist_closed_trade("LONG", True, old, experiment_bucket=bucket)
        for _ in range(2):
            _persist_closed_trade("LONG", False, old, experiment_bucket=bucket)
        for _ in range(5):
            _persist_closed_trade("LONG", True, now - timedelta(hours=1), experiment_bucket=bucket)
        for _ in range(20):
            _persist_closed_trade("LONG", False, now - timedelta(hours=1), experiment_bucket=bucket)

        result = gather_scientific_self_correction(recent_days=7)
        segment = result["segments"][f"experiment_bucket={bucket}"]
        # %92 -> %20 bozulma: yön gerçekten kötüleşmiş ve anlamlı.
        assert segment["original_win_rate"] > segment["recent_win_rate"]
        assert segment["significant_change"] is True
        assert segment["hypothesis_still_valid"] is False
        assert segment["original_sample_size"] == 25
        assert segment["recent_sample_size"] == 25
    finally:
        _cleanup()


def test_gather_scientific_self_correction_excludes_mechanical_strategies():
    """pump_fade/basis_arb kendi risk yönetimlerine sahip mekanik
    stratejiler — council'in isabetini yansıtmadıkları için hiçbir
    segmente karışmamalı (kill switch/concept drift'le AYNI ilke).

    Faz 367-devam — kritik bulgu (2026-08-27): "direction=SHORT hiç
    segmentte olmamalı" iddiası paylaşılan quantdb_test'te YÜZLERCE
    başka testin bıraktığı GERÇEK (mekanik olmayan) SHORT işlemleri
    varsayarak yanlıştı — bu segment doğal olarak var olabilir, test
    onun VARLIĞINI değil bu testin eklediği 50 pump_fade satırının ona
    hiç KATKI vermediğini doğrulamalı. Önce/sonra karşılaştırması,
    _fetch_wins_and_totals'ın gerçek SQL WHERE dışlamasını (bkz. kendi
    docstring'i) hâlâ gerçekten test ederken paylaşılan DB durumundan
    bağımsız hale getiriyor."""
    now = datetime.now(UTC)
    old = now - timedelta(days=30)

    before = gather_scientific_self_correction(recent_days=7)["segments"]
    before_short = before.get("direction=SHORT", {"original_wins": 0, "original_n": 0, "recent_wins": 0, "recent_n": 0})
    before_overall = before.get("overall", {"original_wins": 0, "original_n": 0, "recent_wins": 0, "recent_n": 0})

    try:
        for _ in range(25):
            _persist_closed_trade("SHORT", False, old, experiment_bucket="pump_fade_v1")
        for _ in range(25):
            _persist_closed_trade("SHORT", False, now - timedelta(hours=1), experiment_bucket="pump_fade_v1")

        result = gather_scientific_self_correction(recent_days=7)
        assert "experiment_bucket=pump_fade_v1" not in result["segments"]
        after_short = result["segments"].get(
            "direction=SHORT", {"original_wins": 0, "original_n": 0, "recent_wins": 0, "recent_n": 0}
        )
        after_overall = result["segments"].get(
            "overall", {"original_wins": 0, "original_n": 0, "recent_wins": 0, "recent_n": 0}
        )
        # 50 pump_fade_v1 SHORT kaybı eklendi ama hiçbiri "direction=SHORT"
        # ya da "overall"a sızmamalı — önce/sonra sayaçlar BİREBİR aynı
        # kalmalı (mekanik strateji hiçbir gerçek segmente katkı vermiyor).
        assert after_short == before_short
        assert after_overall == before_overall
    finally:
        _cleanup()


def test_gather_scientific_self_correction_fail_closed_below_min_sample(monkeypatch):
    """Faz 363 — kritik bulgu: bu test önceden GERÇEK, paylaşılan
    quantdb_test'e SADECE 1 kayıt ekleyip result["segments"] == {}
    bekliyordu — ama gather_scientific_self_correction() TÜM decisions
    tablosunu tarıyor (kasıtlı, dashboard'un GERÇEK sistem sağlığını
    görmesi için), sembole göre izole DEĞİL. Bu oturumda paylaşılan test
    DB'sinde biriken binlerce kayıt zaten MIN_SAMPLE_SIZE'ı (20) çoktan
    aştığı için test artık HİÇBİR ZAMAN geçemiyordu — paylaşılan DB
    state'ine bağımlı, kırılgan bir izolasyon varsayımıydı.

    Düzeltme: gerçek DB'ye hiç dokunmadan, _fetch_wins_and_totals'ı
    kontrollü (MIN_SAMPLE_SIZE=20'nin altında) bir veri setiyle mock'layıp
    gatherer'ın GERÇEKTEN fail-closed davrandığını (analytics/
    scientific_self_correction.py::compute_hypothesis_retest'in kendi
    saf-fonksiyon testi zaten bunu doğruluyor — burada SADECE gatherer'ın
    o sonucu doğru ilettiğini/filtrelediğini test ediyoruz) izole olarak
    kanıtlıyor."""
    monkeypatch.setattr(
        "services.scientific_self_correction_gatherer._fetch_wins_and_totals",
        lambda recent_days: {
            "overall": {"original_wins": 5, "original_n": 10, "recent_wins": 5, "recent_n": 10},
        },
    )

    result = gather_scientific_self_correction(recent_days=7)
    assert result["segments"] == {}
