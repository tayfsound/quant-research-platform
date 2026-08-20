"""Decision event contracts."""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    EXPERIMENT = "experiment"
    PAPER = "paper"
    LIVE = "live"


class DecisionEvent(BaseModel):
    """A recorded decision with full provenance."""
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    symbol: str = ""
    proposed_direction: str | None = None
    final_action: str | None = None
    final_size: float = 0.0
    confidence: float = 0.0
    agent_opinions: list[dict] = Field(default_factory=list)
    risk_evaluation: dict | None = None
    market_snapshot: dict | None = None
    belief_state: dict | None = None
    outcome: dict | None = None
    weight_snapshot_id: UUID | None = None
    belief_snapshot_id: UUID | None = None
    decision_latency_ms: float = 0.0
    # Faz 187: gerçek pozisyon yaşam döngüsü (open -> closed), backtest-tarzı
    # anlık ForwardOutcome hesaplamasından ayrı — bkz. services/position_closer.py
    status: str = "no_trade"  # "open" | "closed" | "no_trade"
    entry_price: float | None = None
    exit_price: float | None = None
    quantity: float | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    # Faz 192: RiskTargetStage'in gerçek ATR'den kurduğu risk/ödül
    # magnitüdlerinin (ctx.decision.stop_loss_distance/take_profit_distance),
    # pozisyon gerçekten açıldığı andaki entry_price'a göre mutlak fiyat karşılığı.
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    # Faz 255: kaldıraç desteği — leverage=1.0 spot (kaldıraçsız, önceki
    # davranışla birebir aynı, geriye dönük uyumlu). liquidation_price
    # sadece leverage>1 ise set edilir (bkz. simulator/margin.py::
    # compute_liquidation_price).
    leverage: float = 1.0
    liquidation_price: float | None = None
    # Faz 259: kullanıcı isteği — orta-vadeli pozisyon katmanı. Hangi
    # sinyal zaman diliminden açıldığını (ör. "15m" kısa-vade scalp,
    # "1d" orta-vade swing) SQL ile sorgulanabilir kılıyor — önceden
    # sadece market_snapshot JSON'ı içinde gömülüydü.
    timeframe: str | None = None
    # Faz 250: Live A/B Testing Framework — bu karar bir deneyin (ör.
    # "multi_timeframe_cascade_v1") control/treatment kovasından mı
    # geldi. Deneysel olmayan kararlarda (ezici çoğunluk) None kalır.
    experiment_bucket: str | None = None
    # Faz 315 — Execution Layer, Faz 1. YUKARIDAKİ ExecutionMode enum'uyla
    # ("experiment"/"paper"/"live") KARIŞTIRILMASIN — o, hiçbir production
    # kodunun dokunmadığı ölü bir iskele (engines/live_executor.py'nin
    # kendi kendine yeten stub'ı). Bu alan tamamen ayrı, gerçek bir
    # kavram: "simulated" (varsayılan, bugünkü davranış) | "testnet"
    # (gerçek Binance Futures Testnet emri). Pozisyon açılış anında BİR
    # KEZ yazılır (services/decision_recorder.py) — sonradan global ayar
    # değişse bile zaten açık bir pozisyonun anlamı geriye dönük değişmez.
    execution_mode: str | None = None
    exchange_order_id: str | None = None
    exchange_client_order_id: str | None = None
    exchange_stop_order_id: str | None = None
    exchange_tp_order_id: str | None = None
