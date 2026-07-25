"""Decision Audit Service — immutable karar kaydı."""
from datetime import datetime
from uuid import UUID, uuid4

from contracts.decision_audit import DecisionAuditRecord, ModelOutput
from contracts.repositories import DecisionAuditRepository
from version import PROMPT_VERSION, SCHEMA_VERSION, SYSTEM_VERSION


class DecisionAuditService:
    def __init__(self, repository: DecisionAuditRepository):
        self.repository = repository

    async def record_decision(
        self,
        symbol: str,
        market_snapshot_ref: UUID,
        feature_vector_ref: UUID,
        model_outputs: list[ModelOutput],
        risk_limits: dict[str, float],
        llm_explanation: dict,
        llm_risk_factor: float,
        prompt_hash: str,
        risk_gate_verdict: str,
        final_direction: str,
        final_size: float,
    ) -> DecisionAuditRecord:
        record = DecisionAuditRecord(
            trade_id=uuid4(),
            timestamp=datetime.now(),
            symbol=symbol,
            market_snapshot_ref=market_snapshot_ref,
            feature_vector_ref=feature_vector_ref,
            model_outputs=model_outputs,
            risk_limits_applied=risk_limits,
            llm_explanation=llm_explanation,
            llm_risk_factor=llm_risk_factor,
            prompt_hash=prompt_hash,
            prompt_version=PROMPT_VERSION,
            risk_gate_verdict=risk_gate_verdict,
            final_direction=final_direction,
            final_size=final_size,
            system_version=SYSTEM_VERSION,
            schema_version=SCHEMA_VERSION,
        )
        await self.repository.insert(record)
        return record

    async def get_by_trade_id(self, trade_id: UUID) -> DecisionAuditRecord | None:
        return await self.repository.get_by_trade_id(trade_id)

    async def list_by_symbol(self, symbol: str, limit: int = 100) -> list[DecisionAuditRecord]:
        return await self.repository.list_by_symbol(symbol, limit)
