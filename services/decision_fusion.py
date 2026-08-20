"""Decision Fusion — Expected Value ve Risk/Reward odaklı son karar aşaması."""
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from services.confidence_calibration import calibrate_confidence, get_calibration_curve_for_symbol
from services.inner_critic import InnerCritic


class DecisionFusion:
    def __init__(self):
        self.critic = InnerCritic()

    def evaluate(
        self,
        ctx: CognitiveCycleContext,
        belief: Belief | None = None,
    ) -> CognitiveCycleContext:
        raw_confidence = ctx.decision.confidence or (belief.strength if belief else 0.0)
        # Faz 248: kritik bulgu — gerçek veriyle ölçüldü, beyan edilen
        # confidence sistemli olarak şişirilmiş (%40-60 aralığında gerçek
        # kazanma oranı 20-24 puan daha düşük). EV hesabı ham confidence
        # yerine gerçek geçmiş kararlardan çıkarılan ampirik kalibrasyon
        # eğrisinden geçirilmiş halini kullanıyor — yeterli veri yoksa
        # (fail-closed) ham değer değişmeden kalıyor.
        # Faz 325 — kullanıcı bulgusu: kripto içi büyük-cap/küçük-cap
        # ayrımı gerçek veriyle ölçüldü (35 puanlık fark, bkz. services/
        # confidence_calibration.py::compute_market_cap_tier_calibration_
        # curves üstündeki not) — symbol verilirse önce o eğriye bakılır,
        # yeterli veri yoksa (fail-closed) tek küresel eğriye düşülür.
        curve = get_calibration_curve_for_symbol(ctx.market.symbol)
        confidence = calibrate_confidence(raw_confidence, curve=curve)

        # Faz 268-sonrası — kritik bulgu (üçüncü taraf inceleme + kod
        # doğrulaması): InnerCritic instantiate ediliyordu ama .review()
        # hiç çağrılmıyordu — ürettiği risk_flags/objections tamamen ölü
        # koddu. Artık gerçekten çağrılıyor ve iki sayısal çıktısı
        # (bkz. inner_critic.py) confidence/final_size'ı GERÇEKTEN
        # etkiliyor, sadece açıklanabilirlik için loglanmıyor.
        critique = self.critic.review(ctx)
        if critique["risk_flags"] or critique["objections"]:
            ctx.cognition.relevant_knowledge.append({
                "type": "inner_critic",
                "data": critique,
            })
        confidence *= critique["confidence_multiplier"]

        win = ctx.decision.take_profit or 0.0
        loss = abs(ctx.decision.stop_loss or 0.0)
        ev = confidence * win - (1 - confidence) * loss

        if ev <= 0:
            ctx.decision.action = ActionType.WAIT
            ctx.decision.final_size = 0.0
            ctx.cognition.relevant_knowledge.append({
                "type": "decision_fusion",
                "data": {"rejection": "Negatif beklenen değer (EV)", "ev": round(ev, 6)},
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
                        "rejection": "Hedef, min_profit_target_pct'in altında",
                        "target_pct": round(win / current_price, 6),
                        "min_profit_target_pct": min_profit_target_pct,
                    },
                })
                return ctx

        if critique["size_multiplier"] < 1.0:
            ctx.decision.final_size *= critique["size_multiplier"]
            ctx.cognition.relevant_knowledge.append({
                "type": "decision_fusion",
                "data": {
                    "adjustment": "İç Eleştirmen (InnerCritic) pozisyon boyutunu küçülttü",
                    "size_multiplier": critique["size_multiplier"],
                    "risk_flags": critique["risk_flags"],
                },
            })

        if loss > 0 and win / loss < 0.5:
            ctx.decision.final_size *= 0.5
            ctx.cognition.relevant_knowledge.append({
                "type": "decision_fusion",
                "data": {
                    "adjustment": "Risk/ödül oranı çok düşük, boyut yarıya indirildi",
                    "rr": round(win / loss, 6),
                },
            })

        return ctx
