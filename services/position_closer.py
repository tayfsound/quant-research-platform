"""Faz 187: gerçek pozisyon kapanışı.

services/forward_outcome.py'nin "backtest tarzı" hesaplamasından farkı:
orada entry VE exit aynı anda, aynı zaten-var-olan geçmiş OHLCV penceresinden
okunuyordu (yani hiçbir zaman gerçekten zaman geçmesini beklemiyordu). Burada
entry_price pozisyon gerçekten açıldığı anda sabitlenmiş durumda, exit_price
ise gerçekten şimdi (kapanış anında) çekilen güncel fiyat — aradan gerçekten
en az `hold_seconds` kadar gerçek zaman geçmiş olmalı.
"""
from datetime import UTC, datetime

from contracts.agent_performance import AgentPerformanceRecord
from database.repositories.decision_persistor import DecisionPersistor
from market_data.ingestion.data_provider import OHLCVProvider
from services.agent_memory import AgentMemory
from services.weight_optimizer import WeightOptimizer
from services.weight_repository import WeightRepository
from simulator.fee_engine import FeeEngine

_VALID_AGENT_DOMAINS = {
    "technical", "macro", "onchain", "sentiment",
    "pattern", "quant", "order_flow", "time", "epistemology",
}


class PositionCloser:
    def __init__(
        self,
        data_provider: OHLCVProvider,
        hold_seconds: int = 600,
        fee_engine: FeeEngine | None = None,
    ):
        self.data_provider = data_provider
        self.hold_seconds = hold_seconds
        self.fee_engine = fee_engine or FeeEngine()
        self.agent_memory = AgentMemory()
        self.weight_optimizer = WeightOptimizer(
            agent_memory=self.agent_memory,
            weight_repository=WeightRepository(),
        )

    def _age_seconds(self, opened_at: datetime, now: datetime) -> float:
        # Bilinen borç (CURRENT_STATE.md'de dokümante): DB'de naive/aware
        # datetime karışık olabilir. Burada ikisini de kabul ediyoruz.
        if opened_at.tzinfo is None:
            return (now.replace(tzinfo=None) - opened_at).total_seconds()
        return (now - opened_at).total_seconds()

    def _exit_reason(self, direction: str, current_price: float, stop_loss_price, take_profit_price) -> str | None:
        """Faz 192: gerçek fiyat, gerçek stop/target seviyesine ulaştı mı?
        Vade dolmasını beklemeden hemen kapatmak için — hold_seconds sadece
        hiçbir hedef/stop tanımlı değilse ya da hiçbiri tetiklenmemişse
        devreye giren bir üst sınır."""
        if direction == "LONG":
            if stop_loss_price is not None and current_price <= stop_loss_price:
                return "stop_loss"
            if take_profit_price is not None and current_price >= take_profit_price:
                return "take_profit"
        elif direction == "SHORT":
            if stop_loss_price is not None and current_price >= stop_loss_price:
                return "stop_loss"
            if take_profit_price is not None and current_price <= take_profit_price:
                return "take_profit"
        return None

    def _record_agent_learning(self, pos: dict, pnl: float) -> bool:
        """Faz 210: gerçek bulgu — PositionCloser gerçekten açılıp gerçekten
        kapanan pozisyonların pnl'ini decisions tablosuna yazıyordu, ama
        bu sonucu hiçbir kod AgentMemory/WeightOptimizer'a geri
        beslemiyordu. services/learning_loop.py::process_outcome() bunun
        için yazılmıştı ama onu tetikleyecek tek mekanizma (Pending
        OutcomeTracker.run_scheduler) api/main.py'de kasıtlı olarak
        yorum satırı halinde bırakılmıştı ("TODO: real data_provider
        config"). Üstelik o yol tetiklenmiş olsaydı bile OutcomeTracker.
        attach_outcome() DecisionEvent'i agent_opinions=[] ile kuruyordu —
        gerçek 9 ajan görüşü hiç okunmuyordu. İki katmanlı, tamamen
        kör bir öğrenme yolu. Burada gerçek kapanışın kendi anında,
        decisions.agent_contributions'taki (zaten SELECT * ile elimizde)
        gerçek görüşleri doğrudan AgentMemory'ye yazıyoruz — mevcut
        LearningLoop._apply_feedback ile aynı semantik: işlemin genel
        kârlılığı (pnl>0) her ajanın kaydına uygulanıyor (per-ajan yön
        doğruluğu ayrı bir konu, burada değiştirilmedi)."""
        contributions = pos.get("agent_contributions") or []
        was_correct = pnl > 0
        symbol = pos["symbol"]

        recorded = False
        for item in contributions:
            domain = item.get("domain")
            if domain not in _VALID_AGENT_DOMAINS:
                continue
            self.agent_memory.record(AgentPerformanceRecord(
                agent_domain=domain,
                direction=item.get("direction", ""),
                confidence=item.get("confidence", 0.0) or 0.0,
                was_correct=was_correct,
                pnl=pnl,
                symbol=symbol,
            ))
            recorded = True

        return recorded

    def close_due_positions(self, decision_repo: DecisionPersistor, timeframe: str = "1m") -> list[dict]:
        """Açık pozisyonları gerçek güncel fiyatla kontrol eder: fiyat gerçek
        stop-loss/take-profit seviyesine ulaştıysa hemen kapatır (vade
        beklemeden); ulaşmadıysa ve hold_seconds dolduysa vadeden kapatır.
        Kapatılanların özetini döndürür."""
        now = datetime.now(UTC)
        closed = []
        learned_any = False

        for pos in decision_repo.list_open_positions():
            opened_at = pos.get("opened_at")
            entry_price = pos.get("entry_price")
            if opened_at is None or entry_price is None:
                continue

            symbol = pos["symbol"]
            quantity = pos.get("quantity") or 0.0
            direction = (pos.get("direction") or "").upper()
            age = self._age_seconds(opened_at, now)

            data = self.data_provider.get_ohlcv(symbol, timeframe, limit=1)
            if not data:
                continue
            current_price = data[-1].close

            exit_reason = self._exit_reason(
                direction, current_price, pos.get("stop_loss_price"), pos.get("take_profit_price")
            )
            if exit_reason is None:
                if age < self.hold_seconds:
                    continue
                exit_reason = "time_expired"

            exit_price = current_price

            if direction == "LONG":
                gross_pnl = (exit_price - entry_price) * quantity
            elif direction == "SHORT":
                gross_pnl = (entry_price - exit_price) * quantity
            else:
                gross_pnl = 0.0

            fee = self.fee_engine.calculate(entry_price * quantity) + self.fee_engine.calculate(exit_price * quantity)
            pnl = gross_pnl - fee

            decision_repo.close_position(
                decision_id=str(pos["id"]),
                exit_price=exit_price,
                pnl=pnl,
                closed_at=now,
                outcome={
                    "pnl": pnl,
                    "gross_pnl": gross_pnl,
                    "fee": fee,
                    "win": pnl > 0,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "quantity": quantity,
                    "hold_seconds": age,
                    "exit_reason": exit_reason,
                },
            )
            closed.append({
                "decision_id": str(pos["id"]), "symbol": symbol, "pnl": pnl, "win": pnl > 0,
                "exit_reason": exit_reason,
            })

            if self._record_agent_learning(pos, pnl):
                learned_any = True

        if learned_any and len(self.agent_memory.domains()) > 0:
            self.weight_optimizer.propose_weights(evaluation_window=100)

        return closed
