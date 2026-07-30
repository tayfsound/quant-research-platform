"""Executive Memory — yürütücü kararları ve sonuçlarını saklar."""
from datetime import datetime

from sqlalchemy import text

from contracts.context import CognitiveCycleContext
from database.session_factory import SessionFactory


class ExecutiveMemory:
    def record_decision(self, ctx: CognitiveCycleContext, salience: float, criticism: dict, contradiction: dict) -> dict:
        record = {
            "timestamp": datetime.now().isoformat(),
            "symbol": ctx.market.symbol,
            "salience": salience,
            "proposal": ctx.decision.proposed_direction,
            "final_direction": ctx.decision.final_direction,
            "final_size": ctx.decision.final_size,
            "action": ctx.decision.action.value if ctx.decision.action else "WAIT",
            "reason": ctx.decision.reason.value if ctx.decision.reason else "NO_SIGNAL",
            "confidence": ctx.decision.confidence,
            "uncertainty": ctx.decision.uncertainty,
            "criticism": str(criticism),
            "contradiction": str(contradiction),
        }

        with SessionFactory.get_session() as session:
            session.execute(
                text("""
                INSERT INTO executive_log (timestamp, symbol, salience, proposal, final_direction, final_size, action, reason, confidence, uncertainty, criticism, contradiction)
                VALUES (:timestamp, :symbol, :salience, :proposal, :final_direction, :final_size, :action, :reason, :confidence, :uncertainty, :criticism, :contradiction)
                """),
                record,
            )

        return record
