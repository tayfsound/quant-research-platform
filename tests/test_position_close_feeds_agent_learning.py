"""Faz 210: kritik bulgu — gerçekten kapanan bir pozisyonun pnl'i
decisions tablosuna yazılıyordu ama hiçbir kod bunu AgentMemory/
WeightOptimizer'a geri beslemiyordu (PendingOutcomeTracker.run_scheduler
hiç başlatılmıyordu, ve başlatılsa bile OutcomeTracker.attach_outcome
agent_opinions=[] ile DecisionEvent kuruyordu). PositionCloser artık
kapanışın kendi anında, decisions.agent_contributions'taki gerçek 9 ajan
görüşünü doğrudan AgentMemory'ye yazıyor."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.agent_memory import AgentMemory
from services.position_closer import PositionCloser


class _FixedPriceProvider:
    def __init__(self, price: float):
        self.price = price

    def get_ohlcv(self, symbol, timeframe, limit=1):
        from market_data.ingestion.ohlcv import OHLCV
        now = datetime.now(UTC)
        return [OHLCV(timestamp=now, open=self.price, high=self.price, low=self.price, close=self.price, volume=1.0)]


def test_closing_a_real_position_records_each_real_agent_opinion_into_agent_memory():
    symbol = f"LEARN{uuid4().hex[:8]}"
    now = datetime.now(UTC)

    event = DecisionEvent(
        id=uuid4(),
        timestamp=now - timedelta(minutes=20),
        symbol=symbol,
        proposed_direction="LONG",
        final_action="LONG",
        final_size=1.0,
        confidence=0.7,
        status="open",
        entry_price=100.0,
        quantity=1.0,
        opened_at=now - timedelta(minutes=20),
        # Faz 215: vade dolunca kapatma kaldırıldı — bir pozisyon SADECE
        # gerçekten stop/target'a ulaşınca kapanır, bu yüzden test artık
        # gerçek bir take_profit hedefi tanımlamak zorunda (fiyat 110'a
        # çekilecek, hedef 105 -> tetiklenir).
        stop_loss_price=90.0,
        take_profit_price=105.0,
        agent_opinions=[
            {"domain": "technical", "direction": "LONG", "confidence": 0.8},
            {"domain": "macro", "direction": "SHORT", "confidence": 0.3},
        ],
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)

    memory = AgentMemory()
    before = len(memory._records.get("technical", []))

    closer = PositionCloser(_FixedPriceProvider(price=110.0), hold_seconds=600)
    closer.agent_memory = memory
    with SessionFactory.get_session() as session:
        closed = closer.close_due_positions(DecisionPersistor(session))

    assert any(c["decision_id"] == str(event.id) for c in closed)

    reloaded = AgentMemory()
    after = len(reloaded._records.get("technical", []))
    assert after == before + 1
    # Faz 211: doğruluk artık ajanın KENDİ yönüne göre — genel kârlılığa değil.
    assert reloaded._records["technical"][-1].was_correct is True  # LONG dedi, işlem LONG ve kârlı -> doğru
    assert reloaded._records["macro"][-1].was_correct is False  # SHORT dedi, işlem LONG ve kârlı -> yanlış


def test_closing_a_real_position_records_the_real_market_regime():
    """Faz 258 (mimari inceleme bulgusu, doğrulandı): market_regime hiç
    set edilmiyordu — AgentPerformanceSummary.by_regime, GERÇEK (canlı)
    kapanışlar için her zaman boş/"unknown" kalıyordu. market_snapshot
    zaten decisions.agent_contributions içinde duruyordu, sadece hiç
    okunmuyordu."""
    symbol = f"LEARNREGIME{uuid4().hex[:8]}"
    now = datetime.now(UTC)

    event = DecisionEvent(
        id=uuid4(), timestamp=now - timedelta(minutes=20), symbol=symbol,
        proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
        status="open", entry_price=100.0, quantity=1.0, opened_at=now - timedelta(minutes=20),
        stop_loss_price=90.0, take_profit_price=105.0,
        agent_opinions=[{"domain": "technical", "direction": "LONG", "confidence": 0.8}],
        market_snapshot={"features": {"trend": "bullish"}, "raw_snapshot": {}},
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)

    memory = AgentMemory()
    closer = PositionCloser(_FixedPriceProvider(price=110.0), hold_seconds=600)
    closer.agent_memory = memory
    with SessionFactory.get_session() as session:
        closer.close_due_positions(DecisionPersistor(session))

    reloaded = AgentMemory()
    assert reloaded._records["technical"][-1].market_regime == "bullish"
