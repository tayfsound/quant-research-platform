"""Decision Fusion — Expected Value ve Risk/Reward odaklı son karar aşaması."""
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from services.inner_critic import InnerCritic


class DecisionFusion:
    def __init__(self):
        self.critic = InnerCritic()

    def evaluate(
        self,
        ctx: CognitiveCycleContext,
        belief: Belief | None = None,
    ) -> CognitiveCycleContext:
        confidence = ctx.decision.confidence or (belief.strength if belief else 0.0)
        win = ctx.decision.take_profit or 0.0
        loss = abs(ctx.decision.stop_loss or 0.0)
        ev = confidence * win - (1 - confidence) * loss

        if ev <= 0:
            ctx.decision.action = ActionType.WAIT
            ctx.decision.final_size = 0.0
            ctx.cognition.relevant_knowledge.append({
                "type": "decision_fusion",
                "data": {"rejection": "Negative EV", "ev": round(ev, 6)},
            })
            return ctx

        # Faz 210: kullanıcı bulgusu — ilk gerçek kapanan işlemler (PAXGUSDT,
        # XAUTUSDT) gerçekten take_profit hedefine ulaştı ama komisyon
        # (round-trip ~%0.1) o hedefin ($ olarak, ATR-tabanlı) fiyata oranını
        # (%0.07) aşıyordu — hedefe ulaşmak net zarar demekti. min_profit_
        # target_pct (app_settings, kullanıcı ayarlanabilir), hedefin fiyatın
        # en az bu yüzdesi kadar olmasını zorunlu kılıyor; EV pozitif olsa
        # bile (win/loss oranı üzerinden hesaplanıyor, mutlak $ büyüklüğünü
        # görmüyor) çok küçük bir hedefin komisyonu karşılamadan "kazandırdı"
        # sayılmasını engelliyor.
        current_price = (ctx.market.raw_snapshot or {}).get("close")
        if current_price:
            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.session_factory import SessionFactory

            with SessionFactory.get_session() as session:
                min_profit_target_pct = float(AppSettingsRepository(session).get("min_profit_target_pct"))

            if win / current_price < min_profit_target_pct:
                ctx.decision.action = ActionType.WAIT
                ctx.decision.final_size = 0.0
                ctx.cognition.relevant_knowledge.append({
                    "type": "decision_fusion",
                    "data": {
                        "rejection": "Target below min_profit_target_pct",
                        "target_pct": round(win / current_price, 6),
                        "min_profit_target_pct": min_profit_target_pct,
                    },
                })
                return ctx

        if loss > 0 and win / loss < 0.5:
            ctx.decision.final_size *= 0.5
            ctx.cognition.relevant_knowledge.append({
                "type": "decision_fusion",
                "data": {
                    "adjustment": "R/R too low, size halved",
                    "rr": round(win / loss, 6),
                },
            })

        return ctx
