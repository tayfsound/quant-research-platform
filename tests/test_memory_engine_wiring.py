"""Faz 268i/268j — kritik bulgu, kullanıcı kararıyla acil düzeltildi:
CognitiveEngine.finalize()'ın memory_engine.execute(ctx) çağrısı, HER
cycle'da (gerçek bir pozisyon kapanışı değil, aynı cycle içinde n-bar
ileri hesaplanan sahte bir ForwardOutcome ile) episodic/pgvector hafızaya
yazıyordu. services/decision_context_builder.py (MemoryStage üzerinden,
council oy vermeden ÖNCE HER cycle'da çalışıyor) bu hafızadan "benzer
durumda ne oldu" diye bir MemoryInsight üretip canlı karar motoruna
enjekte ediyordu — yani sahte n-bar sonuçları gerçek kararları
etkiliyordu (Faz 250'nin AgentMemory/WeightOptimizer için kapattığı AYNI
sızıntının bir eşi).

Bu dosya önceden ("Gap #8") tam tersini doğruluyordu — bu yazmanın
gerçekleştiğini kanıtlıyordu. Artık TERSİNİ doğruluyor: finalize()
episodic hafızaya YAZMIYOR (gerçek kapanışlarla beslenene kadar, bkz.
services/cognitive_engine.py::finalize()'ın güncel docstring'i)."""
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.orchestrator import CognitiveOrchestrator


def test_live_cycles_do_not_write_episodes_from_fake_forward_outcome():
    symbol = f"MEMWIRE{uuid4().hex[:8]}"
    orch = CognitiveOrchestrator()
    orch.run_cycle(seed=101, symbol=symbol)
    orch.run_cycle(seed=102, symbol=symbol)

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text("SELECT id FROM episodes WHERE symbol = :symbol"),
            {"symbol": symbol},
        ).mappings().all()

    assert len(rows) == 0


def test_real_position_close_writes_a_real_episode():
    """Faz 268aj — kullanıcı isteği: "bu kısmı [episodic memory] gerçek
    veriyle besleyelim." Faz 268j'nin kestiği sahte n-bar besleme geri
    getirilmedi (yukarıdaki test hâlâ bunu doğruluyor) — bunun yerine
    services/position_closer.py, GERÇEK bir pozisyon gerçekten kapanınca
    (stop/hedef/manuel), gerçek pnl/win/features ile episodic memory'ye
    yazıyor artık."""
    from market_data.ingestion.ohlcv import OHLCV
    from market_data.ingestion.data_provider import OHLCVProvider
    from services.position_closer import PositionCloser

    symbol = f"MEMREAL{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    features = {"RSI": 71.0, "trend": "bearish"}

    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction="SHORT", final_action="SHORT", final_size=1.0, confidence=0.7,
        status="open", entry_price=100.0, quantity=1.0, opened_at=now,
        stop_loss_price=110.0, take_profit_price=80.0,
        market_snapshot={"raw_snapshot": {"close": 100.0}, "features": features},
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)

    class _FixedPriceProvider(OHLCVProvider):
        def get_ohlcv(self, symbol, timeframe, limit=1):
            return [OHLCV(timestamp=now, open=112.0, high=112.0, low=112.0, close=112.0, volume=1.0)]

    closer = PositionCloser(_FixedPriceProvider(), hold_seconds=3600)
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))
    assert any(c["decision_id"] == str(event.id) for c in closed)

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text("SELECT symbol, decision, outcome, embedding FROM episodes WHERE symbol = :symbol"),
            {"symbol": symbol},
        ).mappings().all()

    assert len(rows) == 1
    assert rows[0]["decision"] == "SHORT"
    assert rows[0]["outcome"]["win"] is False  # SHORT, fiyat yükseldi -> stop -> gerçek kayıp
    assert rows[0]["embedding"] is not None  # semantic search'ün bulabilmesi için gerçek vektör var
