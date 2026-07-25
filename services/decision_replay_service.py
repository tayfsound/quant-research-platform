"""Decision Replay Service — geçmiş kararı güncel modellerle yeniden oynat."""
from uuid import UUID

from contracts.repositories import DecisionAuditRepository


class DecisionReplayService:
    def __init__(self, audit_repo: DecisionAuditRepository):
        self.audit_repo = audit_repo
        self._current_explainer = None  # LLMExplainerPort (sonradan enjekte edilecek)

    async def replay(self, trade_id: UUID) -> dict:
        """Geçmiş kararı bul, güncel modellerle yeniden değerlendir."""
        record = await self.audit_repo.get_by_trade_id(trade_id)
        if not record:
            return {"error": f"Trade {trade_id} not found"}

        # TODO: Feature vector ve market snapshot'ı yükle
        # TODO: Güncel modellerle inference yap
        # TODO: Risk gate'den geçir
        # TODO: Sonucu karşılaştır

        return {
            "trade_id": str(trade_id),
            "symbol": record.symbol,
            "original_direction": record.final_direction,
            "original_size": record.final_size,
            "original_llm_factor": record.llm_risk_factor,
            "new_direction": "PENDING",  # Gerçek implementasyon Faz 162'de
            "diff": "Not yet implemented",
        }
