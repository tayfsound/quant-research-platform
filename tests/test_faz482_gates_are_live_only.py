"""Faz 482 — kullanıcı bulgusu (2026-09-10): "sadece live modu için geçerli
olacak kapılar bunlar, test moduna engel olmaması lazımdı."

Gerçek canlı ölçüm: `decision_recorder.py`'deki 10 post-hoc kapı
trading_mode'a HİÇ bakmıyordu. 9 Eylül'de min_confidence_gate TEK BAŞINA
3074 kararı blokladı ve açılma oranı %30,7'den %1,2'ye düştü — oysa
sembollerin 123'ünün 119'u tamamen simüle, ortada korunacak gerçek sermaye
yoktu. Faz 397'nin strategy_regime_gate için kurduğu carve-out deseni
(`gate_bypassed_test_mode`) artık 10 kapının HEPSİ için geçerli.

Bu dosya üç şeyi doğruluyor:
  1. Gerçek borsaya giden sembolde kapı AYNEN engelliyor (koruma duruyor).
  2. Simüle sembolde engellemiyor ama kapı yine DEĞERLENDİRİLİYOR ve
     `gate_bypassed_test_mode` olarak kaydediliyor (ölçüm körleşmiyor).
  3. trading_mode="test" tek başına da carve-out'u tetikliyor.
"""
import uuid

import pytest

from contracts.context import CognitiveCycleContext
from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from services.decision_recorder import DecisionRecorder
from tests.live_gate_helpers import symbol_on_real_exchange


@pytest.fixture(autouse=True)
def _min_confidence_gate_on():
    """Paylaşılan quantdb_test'te `min_confidence_gate_enabled` başka
    testlerin bıraktığı "false" değeriyle duruyor olabilir (gerçekten
    öyleydi) — bu dosyanın konusu kapının carve-out davranışı, kapının
    kendisinin açık olup olmadığı değil. Kapıyı testin kendisi kuruyor,
    sonunda eski değeri geri yazıyor."""
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        before_enabled = repo.get("min_confidence_gate_enabled")
        before_min = repo.get("min_confidence_gate_min_confidence")
        repo.set("min_confidence_gate_enabled", "true", updated_by="test")
        repo.set("min_confidence_gate_min_confidence", "0.7", updated_by="test")
    try:
        yield
    finally:
        with SessionFactory.get_session() as session:
            repo = AppSettingsRepository(session)
            repo.set(
                "min_confidence_gate_enabled",
                before_enabled if before_enabled is not None else "true",
                updated_by="test",
            )
            repo.set(
                "min_confidence_gate_min_confidence",
                before_min if before_min is not None else "0.7",
                updated_by="test",
            )

# Faz 421'in canlı varsayılanı: min_confidence_gate AÇIK, taban 0.7.
# Bu dosya onu temsilci kapı olarak kullanıyor — carve-out mekanizması
# kapıdan bağımsız, ortak `_apply_gate()` üzerinden çalışıyor.
_BLOCKED_CONFIDENCE = 0.40


def _ctx(symbol: str, trading_mode: str = "live") -> CognitiveCycleContext:
    return CognitiveCycleContext(
        market={
            "symbol": symbol,
            "raw_snapshot": {"close": 100.0},
            "features": {"trend": "bullish", "volatility_regime": "normal"},
        },
        decision={
            "proposed_direction": "LONG", "final_action": "LONG",
            "final_size": 10.0, "stop_loss_distance": 3.0, "take_profit_distance": 3.0,
            "confidence": _BLOCKED_CONFIDENCE,
        },
        risk={"evaluation": {"verdict": "approved"}, "trading_mode": trading_mode},
    )


def _gate_entries(event, entry_type: str, gate: str) -> list:
    return [
        o for o in event.agent_opinions
        if o.get("type") == entry_type and (o.get("data") or {}).get("gate") == gate
    ]


def test_gate_still_blocks_a_symbol_that_routes_to_a_real_exchange():
    """Koruma testi — carve-out'un gerçek sermayeyi açıkta bırakMAdığı."""
    symbol = f"F482L{uuid.uuid4().hex[:6]}USDT"
    with symbol_on_real_exchange(symbol):
        event = DecisionRecorder().record(_ctx(symbol), [])

    assert event.status == "no_trade"
    assert len(_gate_entries(event, "gate_block", "min_confidence_gate")) == 1
    assert not _gate_entries(event, "gate_bypassed_test_mode", "min_confidence_gate")


def test_gate_does_not_block_a_simulated_symbol_but_still_records_its_verdict():
    """ASIL düzeltme: simüle sembolde pozisyon açılıyor AMA kapının ne
    yapacağı kaydediliyor — `analytics/gate_selection_value.py`'nin
    ölçtüğü "engelleseydi ne olurdu" örneklemi kaybolmuyor."""
    symbol = f"F482S{uuid.uuid4().hex[:6]}USDT"
    event = DecisionRecorder().record(_ctx(symbol), [])

    assert event.status == "open"
    bypassed = _gate_entries(event, "gate_bypassed_test_mode", "min_confidence_gate")
    assert len(bypassed) == 1
    # Kapının teşhis verisi aynen korunuyor (sadece etiket değişiyor).
    assert bypassed[0]["data"]["confidence"] == _BLOCKED_CONFIDENCE
    assert bypassed[0]["data"]["min_confidence"] == 0.7
    assert not _gate_entries(event, "gate_block", "min_confidence_gate")


def test_test_trading_mode_alone_triggers_the_carveout_even_on_a_real_exchange_symbol():
    """Faz 454'ün negatif-EV carve-out'uyla AYNI kural: `trading_mode="test"`
    VEYA simüle sembol. Test modunda gerçek sermaye riski tanım gereği yok."""
    symbol = f"F482T{uuid.uuid4().hex[:6]}USDT"
    with symbol_on_real_exchange(symbol):
        event = DecisionRecorder().record(_ctx(symbol, trading_mode="test"), [])

    assert event.status == "open"
    assert len(_gate_entries(event, "gate_bypassed_test_mode", "min_confidence_gate")) == 1
