"""Shadow Position repository — Faz 268-sonrası (Shadow Mode: Macro-Only karşılaştırma)."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, String
from sqlalchemy.dialects.postgresql import UUID

from contracts.shadow_position import ShadowPosition
from database.base import Base


class ShadowPositionModel(Base):
    __tablename__ = "shadow_positions"
    id = Column(UUID(as_uuid=True), primary_key=True)
    source = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    direction = Column(String, nullable=False)
    confidence = Column(Float, nullable=True)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    stop_loss_price = Column(Float, nullable=False)
    take_profit_price = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="open")
    pnl_pct = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True)
    opened_at = Column(DateTime, nullable=False)
    closed_at = Column(DateTime, nullable=True)


class ShadowPositionRepository:
    def __init__(self, session):
        self.session = session

    def open_position(self, position: ShadowPosition) -> None:
        row = ShadowPositionModel(
            id=position.id,
            source=position.source,
            symbol=position.symbol,
            direction=position.direction,
            confidence=position.confidence,
            entry_price=position.entry_price,
            stop_loss_price=position.stop_loss_price,
            take_profit_price=position.take_profit_price,
            status="open",
            opened_at=position.opened_at,
        )
        self.session.add(row)
        self.session.commit()

    def has_open_position(self, source: str, symbol: str) -> bool:
        return (
            self.session.query(ShadowPositionModel)
            .filter_by(source=source, symbol=symbol, status="open")
            .first()
            is not None
        )

    def list_open(self, source: str | None = None) -> list[ShadowPositionModel]:
        query = self.session.query(ShadowPositionModel).filter_by(status="open")
        if source is not None:
            query = query.filter_by(source=source)
        return query.all()

    def close_position(
        self, position_id, exit_price: float, exit_reason: str, closed_at: datetime
    ) -> float:
        row = self.session.query(ShadowPositionModel).filter_by(id=position_id).one()
        sign = 1.0 if row.direction == "LONG" else -1.0
        pnl_pct = sign * (exit_price - row.entry_price) / row.entry_price

        row.status = "closed"
        row.exit_price = exit_price
        row.exit_reason = exit_reason
        row.pnl_pct = pnl_pct
        row.closed_at = closed_at
        self.session.commit()
        return pnl_pct

    def comparison_summary(self, source: str = "macro", min_sample_size: int = 100) -> dict:
        """100+ kapanmış gölge pozisyon birikince Macro-Only'nin gerçek
        performansını (win_rate, avg_pnl_pct) döndürür. sample_size_
        sufficient=False iken de sayılar döner (şeffaflık için) ama
        kullanıcıya "henüz kanıt sayılmaz" sinyali net verilir — Feature
        IC/LLM Audit ile AYNI "ölç ama otomatik eyleme geçme" ilkesi."""
        rows = (
            self.session.query(ShadowPositionModel)
            .filter_by(source=source, status="closed")
            .all()
        )
        total = len(rows)
        if total == 0:
            return {
                "source": source,
                "closed_count": 0,
                "win_rate": None,
                "avg_pnl_pct": None,
                "cumulative_pnl_pct": None,
                "max_drawdown_pct": None,
                "sample_size_sufficient": False,
            }

        wins = sum(1 for r in rows if (r.pnl_pct or 0.0) > 0)
        pnl_series = [r.pnl_pct or 0.0 for r in sorted(rows, key=lambda r: r.closed_at)]
        cumulative = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for pnl in pnl_series:
            cumulative += pnl
            peak = max(peak, cumulative)
            max_drawdown = min(max_drawdown, cumulative - peak)

        return {
            "source": source,
            "closed_count": total,
            "win_rate": round(wins / total, 3),
            "avg_pnl_pct": round(sum(pnl_series) / total, 5),
            "cumulative_pnl_pct": round(cumulative, 5),
            "max_drawdown_pct": round(max_drawdown, 5),
            "sample_size_sufficient": total >= min_sample_size,
        }
