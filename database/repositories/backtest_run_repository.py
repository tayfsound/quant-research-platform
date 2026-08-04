"""Backtest run repository — Class 2 persistent data, no delete/update methods
by design (results must remain independently re-verifiable)."""
from sqlalchemy import Column, DateTime, Float, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID

from database.base import Base
from contracts.backtest_run import BacktestRun


class BacktestRunModel(Base):
    __tablename__ = "backtest_runs"
    id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    symbols = Column(JSON, nullable=False)
    git_sha = Column(String(40), nullable=False)
    weight_snapshot_id = Column(UUID(as_uuid=True), nullable=True)
    fee = Column(Float, nullable=False)
    lookback = Column(Integer, nullable=False)
    num_bars = Column(Integer, nullable=False)
    total_pnl = Column(Float, nullable=False)
    per_symbol_pnl = Column(JSON, nullable=False)
    metrics = Column(JSON, nullable=False)
    equity_curve = Column(JSON, nullable=False)


class BacktestRunRepository:
    def __init__(self, session):
        self.session = session

    def save(self, run: BacktestRun) -> BacktestRun:
        row = BacktestRunModel(
            id=run.id,
            created_at=run.created_at,
            symbols=run.symbols,
            git_sha=run.git_sha,
            weight_snapshot_id=run.weight_snapshot_id,
            fee=run.fee,
            lookback=run.lookback,
            num_bars=run.num_bars,
            total_pnl=run.total_pnl,
            per_symbol_pnl=run.per_symbol_pnl,
            metrics=run.metrics,
            equity_curve=run.equity_curve,
        )
        self.session.add(row)
        self.session.commit()
        return run

    def get_by_id(self, run_id) -> BacktestRunModel | None:
        return self.session.query(BacktestRunModel).filter_by(id=run_id).first()

    def list_recent(self, limit: int = 20) -> list[BacktestRunModel]:
        return (
            self.session.query(BacktestRunModel)
            .order_by(BacktestRunModel.created_at.desc())
            .limit(limit)
            .all()
        )
