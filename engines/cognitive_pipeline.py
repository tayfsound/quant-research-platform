"""Cognitive Pipeline Aşamaları — opinions akışı + Debate hafızası + RecordingStage."""
from contracts.contexts.decision import ActionType
from contracts.contexts.risk import RiskReason

from agents.registry import AgentRegistry
from contracts.agent import AgentDomain, AgentOpinion
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.decision_event import DecisionEvent
from contracts.experiment_registry import ExperimentRegistry
from services.context_adapter import ContextAdapter
from services.council_orchestrator import CouncilOrchestrator
from services.decision_context_builder import DecisionContextBuilder
from services.decision_fusion import DecisionFusion
from services.decision_recorder import DecisionRecorder
from services.kelly_sizing import kelly_size_multiplier
from services.knowledge_base import KnowledgeBase
from services.metacognition import Metacognition


class MemoryStage:
    def __init__(self):
        self.context_builder = DecisionContextBuilder()

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        return self.context_builder.enrich(ctx)


class KnowledgeStage:
    def __init__(self, knowledge_base: KnowledgeBase | None = None):
        self.knowledge_base = knowledge_base or KnowledgeBase()

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        relevant = self.knowledge_base.query_relevant(
            ctx.market.model_dump(),
            ctx.decision.model_dump(),
        )
        ctx.cognition.relevant_knowledge.extend(relevant)
        return ctx


class CouncilStage:
    def __init__(self, registry: AgentRegistry, pinned_weight_snapshot_id=None):
        self.registry = registry
        self.adapter = ContextAdapter()
        self.orchestrator = CouncilOrchestrator(
            registry, pinned_weight_snapshot_id=pinned_weight_snapshot_id
        )
        self.knowledge_base = KnowledgeBase()

    def execute(self, ctx: CognitiveCycleContext) -> tuple[CognitiveCycleContext, Belief, list[AgentOpinion]]:
        wisdom = self.knowledge_base.query_relevant(
            ctx.market.model_dump(),
            ctx.decision.model_dump(),
        )
        for w in wisdom:
            ctx.cognition.relevant_knowledge.append(w)

        contexts = {
            AgentDomain.MACRO: self.adapter.to_macro(ctx),
            AgentDomain.SENTIMENT: self.adapter.to_sentiment(ctx),
            AgentDomain.ONCHAIN: self.adapter.to_onchain(ctx),
            AgentDomain.TECHNICAL: self.adapter.to_technical(ctx),
            AgentDomain.PATTERN: self.adapter.to_pattern(ctx),
            AgentDomain.QUANT: self.adapter.to_quant(ctx),
            AgentDomain.ORDER_FLOW: self.adapter.to_order_flow(ctx),
            AgentDomain.TIME: self.adapter.to_time(ctx),
            AgentDomain.EPISTEMOLOGY: self.adapter.to_epistemology(ctx),
        }

        # Faz 268b — Regime-Aware Learning: PositionCloser._record_agent_
        # learning'in kapanmış işlemleri etiketlediği AYNI format
        # ("trend_volatility") — bu ikisi eşleşmezse regime-özel
        # snapshot'lar hiçbir zaman doğru anda seçilmez.
        features = ctx.market.features or {}
        trend = features.get("trend", "unknown")
        current_regime = f"{trend}_{features.get('volatility_regime', 'normal')}" if trend != "unknown" else None

        belief, opinions = self.orchestrator.deliberate(contexts, regime=current_regime)

        ctx.cognition.relevant_knowledge.append({
            "type": "weight_snapshot",
            "data": {
                "id": str(self.orchestrator.active_weight_snapshot_id)
                if self.orchestrator.active_weight_snapshot_id
                else None
            },
        })

        ctx.cognition.relevant_knowledge.append({
            "type": "council_belief",
            "data": belief.model_dump(),
        })

        # Debate katmanı çıktısını bilişsel hafızaya kaydet
        if self.orchestrator.last_debate_result:
            ctx.cognition.relevant_knowledge.append({
                "type": "debate_result",
                "data": self.orchestrator.last_debate_result.model_dump(),
            })

        return ctx, belief, opinions


class MetaStage:
    def __init__(self):
        self.metacognition = Metacognition()

    def execute(self, ctx: CognitiveCycleContext, belief: Belief) -> CognitiveCycleContext:
        # Faz 204: eşikler artık app_settings'ten okunuyor — başlangıçta
        # dürüst varsayılan (%70/%40, hiç kalibre edilmemiş) ama
        # services/threshold_optimizer.py yeterli gerçek kapalı işlem
        # birikince (min. 20) bunları GERÇEK kâr/zarar geçmişine göre
        # güncelleyebiliyor (bkz. optimize_thresholds_task).
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            self.metacognition.act_threshold = float(settings_repo.get("act_threshold"))
            self.metacognition.reduce_threshold = float(settings_repo.get("reduce_threshold"))

        # Faz 207: kullanıcı isteği — "test modundayken güven olmasa da bir
        # şeyler yapsın, deneyim kazansın; hataları gerçek kayıp
        # yaratmıyorken onu neden kısıtlıyoruz?" Gerçek bir nokta: services/
        # threshold_optimizer.py ve weight_optimizer gibi öğrenme
        # mekanizmalarının hepsi gerçek kapanmış işlem geçmişine ihtiyaç
        # duyuyor, ama reduce_threshold (0.4) test modunda bile aynı sıkılıkta
        # uygulandığı için belief.direction gerçekten LONG/SHORT olsa bile
        # (WAIT değil — o zaten aşağıda RiskTargetStage/DecisionFusion'da
        # ayrıca elenir) zayıf ama gerçek bir yönlü sinyal hiç açılmadan
        # WAIT'e düşüyordu, sistem hiç gerçek sonuç biriktiremiyordu. Test
        # modunda tabanı neredeyse sıfıra indiriyoruz — REDUCE zaten
        # büyüklüğü confidence ile orantılı küçültüyor (final_size =
        # proposed_size * confidence), yani zayıf sinyal otomatik olarak
        # küçük pozisyon açıyor, büyük risk almıyor. act_threshold (tam
        # büyüklük için gereken gerçek konviksiyon çıtası) test modunda da
        # aynı kalıyor — "her sinyal tam büyüklük" değil, "her yönlü sinyal
        # bir şans" istiyoruz.
        if ctx.risk.trading_mode == "test":
            self.metacognition.reduce_threshold = 0.05

        conflict_level = max(
            belief.cluster_disagreement,
            belief.crowding_penalty,
            belief.uncertainty,
        )

        criticism = {"risk_flags": []}

        if belief.cluster_balance < 0.3:
            criticism["risk_flags"].append("low_cluster_balance")

        if belief.crowding_penalty > 0.5:
            criticism["risk_flags"].append("high_crowding")

        # Faz 203: kritik bulgu — belief.strength (Council'in bu cycle'da
        # GERÇEKTEN ne kadar güçlü/tutarlı bir konsensüse vardığı, services/
        # belief_engine.py'de gerçek ağırlıklı oylardan hesaplanıyor) buraya
        # hiç iletilmiyordu. evaluate_confidence sadece hafızaya bakıp
        # (hafıza yoksa sabit 0.5) confidence üretiyordu — 9 ajan bile
        # birleşse ACT eşiğine (0.7) asla ulaşamıyordu.
        meta = self.metacognition.evaluate_confidence(
            ctx,
            criticism,
            {"conflict_level": conflict_level},
            belief_strength=belief.strength,
            belief_direction=belief.direction,
        )

        ctx.decision.confidence = meta["confidence"]
        ctx.decision.uncertainty = meta["uncertainty"]
        if meta["decision"] == "WAIT":
            ctx.decision.action = ActionType.WAIT
            ctx.decision.final_size = 0.0

        elif meta["decision"] == "REDUCE":
            ctx.decision.action = ActionType.REDUCE
            ctx.decision.final_size = ctx.decision.proposed_size * meta["confidence"]

        else:
            # Faz 206: gerçek bulgu — ACT dalı action'ı LONG/SHORT'a
            # çeviriyordu ama final_size'ı HİÇ set etmiyordu (WAIT ve REDUCE
            # dalları set ediyor). PAXGUSDT confidence=0.78 (act_threshold
            # 0.7'nin üstünde) ile gerçek bir ACT kararı üretilirken bile
            # final_size Decision contract'ının varsayılanı olan 0.0'da
            # kalıyordu — DecisionRecorder.opens_position final_size>0
            # şartını hiç sağlayamıyor, "onaylanmış ACT" bile hiçbir zaman
            # gerçek pozisyon açmıyordu.
            #
            # Faz 268g — "İsabeti artırmanın yolu daha akıllı kullanım" yol
            # haritasının D fazı (Signal-Strength Position Sizing). REDUCE
            # dalı zaten confidence'a orantılı küçülüyordu ama ACT dalı
            # confidence=0.71 ile 0.99'u AYNI (tam) büyüklükte açıyordu —
            # hiç ayrım yoktu. Artık o confidence kovasının GERÇEK geçmiş
            # kazanç/kayıp dağılımından (half-Kelly) bir çarpan uygulanıyor
            # — [0,1] aralığında, sadece küçültebilir, asla büyütemez;
            # yeterli veri yoksa (fail-closed) 1.0, mevcut davranış aynen
            # korunur.
            kelly_multiplier = kelly_size_multiplier(meta["confidence"])
            if belief.direction == "LONG":
                ctx.decision.action = ActionType.ENTER_LONG
                ctx.decision.final_size = ctx.decision.proposed_size * kelly_multiplier
            elif belief.direction == "SHORT":
                ctx.decision.action = ActionType.ENTER_SHORT
                ctx.decision.final_size = ctx.decision.proposed_size * kelly_multiplier
            else:
                ctx.decision.action = ActionType.WAIT
                ctx.decision.final_size = 0.0

        ctx.decision.proposed_direction = belief.direction

        return ctx


class RiskTargetStage:
    """Faz 191 — gerçek bulgu: DecisionFusion (aşağıda) `ctx.decision.
    take_profit`/`stop_loss`'a bakıp Expected Value hesaplıyordu, ama
    hiçbir kod bu iki alanı hiçbir zaman set etmiyordu (hep None) — yani
    win=0, loss=0, ev her zaman <=0, Council ne önerirse önersin HER
    işlem WAIT'e zorlanıyordu. Bu aşama, MetaStage'in belirlediği yön için
    standart bir 1:2.5 risk/ödül hedefi kuruyor — icat edilmiş bir
    "hedef fiyat" değil, ATR-tabanlı stop literatürde yaygın, kesin
    tanımlı bir yöntem.

    Faz 251: kritik bulgu — önceden sinyal zaman diliminin (candle_
    timeframe, genelde 1m) ATR'sini kullanıyordu. 1 dakikalık ATR kripto
    gibi yüksek volatiliteli bir piyasada bile gürültü seviyesinde kalıyor
    (gerçek ölçüm: BTCUSDT 1m ATR fiyatın ~%0.05'i) — stop, bir mumun
    sıradan dalgalanmasından bile küçük kalıp anında tetikleniyordu,
    kazanma oranı düşük kalıyordu çünkü yöne hiç şans tanınmıyordu
    (kullanıcı bulgusu, gerçek kapanmış işlemlerle doğrulandı: $1900'lük
    pozisyonlarda $0.07 stop, $0.15 hedef gibi anlamsız değerler).
    Kullanıcıyla üzerinde anlaşılan çerçeve: risk sinyal zaman diliminden
    BAĞIMSIZ, günlük ATR'den (signal_engine.compute_daily_atr_pct)
    türetiliyor — 2.5x günlük ATR (şu an BTCUSDT için ~%5.3 stop mesafesi,
    literatürdeki standart 2-3x ATR-stop aralığında). Günlük ATR yoksa
    (yetersiz veri) hedef set edilmez — DecisionFusion hâlâ (doğru
    şekilde) reddeder.

    Faz 261 — kritik bulgu: 1:2 hedef/stop oranı (yukarıdaki 2.5x/5.0x)
    services/confidence_calibration.py'nin GERÇEK verilerle ölçtüğü
    kalibrasyon eğrisiyle çelişiyordu — %40-60 aralığındaki ham güven
    kalibre edildiğinde %21-29'a düşüyor (bkz. confidence_calibration.py
    üstündeki not), ama 1:2 oranında kâra geçmek için %33.3 gerekiyordu.
    Sonuç: konseyin ürettiği kararların neredeyse tamamı (canlıda
    doğrulandı: 30 dakikada watchlist genelinde 30/30 yönlü karar)
    DecisionFusion'ın "Negative EV" kapısında reddediliyordu — sistem
    fiilen işlem açmayı durdurmuştu. Oran 1:4'e genişletildi: %21-29
    aralığındaki kalibre güven artık (%20 breakeven'in üzerinde) kâra
    geçiyor. Bilinen çekince (kullanıcıyla paylaşıldı): kalibrasyon
    eğrisi şu an ağırlıklı olarak ESKİ (Faz 251 öncesi, gürültü
    seviyesinde stop'larla açılmış) kapanmış işlemlerden hesaplanıyor —
    yeni rejim altında yeterli (~30-50) gerçek kapanış birikince bu oran
    gerçek, temiz veriyle yeniden değerlendirilecek."""
    STOP_ATR_MULT = 2.5
    TARGET_ATR_MULT = 10.0

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        direction = (ctx.decision.proposed_direction or "").upper()
        if direction not in ("LONG", "SHORT"):
            return ctx

        daily_atr_pct = (ctx.market.features or {}).get("daily_atr_pct")
        current_price = (ctx.market.raw_snapshot or {}).get("close")
        if not daily_atr_pct or daily_atr_pct <= 0 or not current_price or current_price <= 0:
            return ctx

        ctx.decision.stop_loss = current_price * self.STOP_ATR_MULT * daily_atr_pct
        ctx.decision.take_profit = current_price * self.TARGET_ATR_MULT * daily_atr_pct
        return ctx


class DecisionFusionStage:
    def __init__(self):
        self.fusion = DecisionFusion()

    def execute(self, ctx: CognitiveCycleContext, belief: Belief) -> CognitiveCycleContext:
        return self.fusion.evaluate(ctx, belief)


class BinderStage:
    """Knowledge -> CognitiveBinding -> Belief (P0-5 bind)."""
    def __init__(self):
        from services.cognitive_binder import CognitiveBinder
        self.binder = CognitiveBinder()

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        for item in ctx.cognition.relevant_knowledge:
            if item.get("type") == "wisdom":
                from contracts.expression import Expression, Constant
                from contracts.cognitive_binding import CognitiveBinding
                expr = Expression(
                    name=item.get("category", "unknown"),
                    description=item.get("principle", ""),
                    root=Constant(value=item.get("confidence", 0.5)),
                )
                binding = CognitiveBinding(
                    source_type="knowledge_base",
                    expression=expr,
                    confidence=item.get("confidence", 0.5),
                    evidence_count=item.get("validation_count", 0),
                )
                belief = self.binder.knowledge_to_belief(binding)
                ctx.cognition.relevant_knowledge.append({
                    "type": "binder_belief",
                    "data": belief.model_dump(),
                })
        return ctx



class RecordingStage:
    def __init__(self):
        self.recorder = DecisionRecorder()

    def execute(
        self,
        ctx: CognitiveCycleContext,
        belief: Belief,
        opinions: list[AgentOpinion],
    ) -> DecisionEvent:

        debate_result = None
        weight_snapshot_id = None
        # Faz 212: gerçek bulgu — DecisionFusion.evaluate()'in ret nedeni
        # (Negative EV, ya da Faz 210c'nin min_profit_target_pct reddi)
        # ctx.cognition.relevant_knowledge'a yazılıyordu ama bu liste
        # decisions.agent_contributions'a HİÇ aktarılmıyordu (debate_result/
        # weight_snapshot gibi elle çekilmiyordu) — "neden reddedildi?"
        # sorusunun cevabı DB'de hiç yoktu, her seferinde canlı kod
        # çalıştırıp yeniden üretmek gerekiyordu.
        decision_fusion_entries = []

        if hasattr(ctx, "cognition"):
            for item in ctx.cognition.relevant_knowledge:
                if item.get("type") == "decision_fusion":
                    decision_fusion_entries.append(item.get("data"))

            for item in reversed(ctx.cognition.relevant_knowledge):
                if item.get("type") == "debate_result":
                    debate_result = item.get("data")

                if item.get("type") == "weight_snapshot":
                    weight_snapshot_id = item.get("data", {}).get("id")

                if debate_result and weight_snapshot_id:
                    break

        event = self.recorder.record(
            ctx,
            opinions,
            belief,
            debate_result,
            weight_snapshot_id,
            decision_fusion_entries,
        )

        from observability.metrics import decisions_total
        decisions_total.labels(
            symbol=ctx.market.symbol or "unknown",
            action=str(getattr(ctx.decision, "action", "") or event.final_action or "WAIT"),
        ).inc()

        ctx.cognition.relevant_knowledge.append({
            "type": "decision_event",
            "data": event.model_dump(),
        })

        # Belief persistence -- pipeline'dan DB'ye (P0-6)
        if belief is not None:
            from services.memory_service import MemoryService
            MemoryService().store_belief(belief)

        return event


class RiskGateStage:
    """Post-fusion risk gate — evaluates final_size against signed limits."""

    def __init__(self, risk_engine):
        self.risk_engine = risk_engine

    def execute(self, ctx):
        # Faz 190: Start/Stop düğmesi — bkz. risk_engine.py.
        if not ctx.risk.ai_enabled:
            ctx.risk.evaluation.verdict = "rejected"
            ctx.risk.evaluation.reasons = [RiskReason(
                code="AI_STOPPED",
                message="AI is stopped (dashboard Start/Stop) — no new positions",
                severity="info",
            )]
            return ctx

        # Faz 189: cooldown, test modunda bile atlanmaz (bkz. risk_engine.py).
        if (
            ctx.risk.seconds_since_last_trade is not None
            and ctx.risk.min_seconds_between_trades is not None
            and ctx.risk.seconds_since_last_trade < ctx.risk.min_seconds_between_trades
        ):
            ctx.risk.evaluation.verdict = "rejected"
            ctx.risk.evaluation.reasons = [RiskReason(
                code="COOLDOWN_ACTIVE",
                message=(
                    f"{ctx.risk.seconds_since_last_trade:.0f}s < "
                    f"{ctx.risk.min_seconds_between_trades}s cooldown"
                ),
                severity="info",
            )]
            return ctx

        # Faz 188: test modunda hem ön hem son risk kapısı devre dışı.
        if ctx.risk.trading_mode == "test":
            ctx.risk.evaluation.verdict = "approved"
            return ctx

        limits = ctx.risk.limits
        final_size = getattr(ctx.decision, "final_size", 0.0)
        reasons = []

        max_size = limits.get("max_position_size")
        if max_size and final_size > max_size.value:
            reasons.append(RiskReason(
                code="POST_FUSION_SIZE_EXCEEDED",
                message="Final size " + str(final_size) + " > limit " + str(max_size.value),
                severity="critical",
            ))

        max_dd = limits.get("max_drawdown")
        if max_dd and ctx.risk.current_drawdown >= max_dd.value:
            reasons.append(RiskReason(
                code="MAX_DRAWDOWN",
                message="Drawdown exceeded",
                severity="critical",
            ))

        max_lev = limits.get("max_leverage")
        if max_lev and getattr(ctx.risk, "current_leverage", 0) > max_lev.value:
            reasons.append(RiskReason(
                code="MAX_LEVERAGE_EXCEEDED",
                message="Leverage exceeded",
                severity="critical",
            ))

        daily_loss = limits.get("daily_loss_limit")
        if daily_loss and getattr(ctx.risk, "daily_pnl", 0) <= -daily_loss.value:
            reasons.append(RiskReason(
                code="DAILY_LOSS_LIMIT",
                message="Daily loss limit exceeded",
                severity="critical",
            ))

        if ctx.risk.max_concurrent_positions is not None and ctx.risk.open_position_count >= ctx.risk.max_concurrent_positions:
            reasons.append(RiskReason(
                code="MAX_CONCURRENT_POSITIONS",
                message=f"{ctx.risk.open_position_count} open >= limit {ctx.risk.max_concurrent_positions}",
                severity="critical",
            ))

        if ctx.risk.max_capital_pct is not None and ctx.risk.capital_used_pct >= ctx.risk.max_capital_pct:
            reasons.append(RiskReason(
                code="MAX_CAPITAL_PCT",
                message=f"{ctx.risk.capital_used_pct:.1%} used >= limit {ctx.risk.max_capital_pct:.1%}",
                severity="critical",
            ))

        if reasons:
            ctx.decision.action = ActionType.WAIT
            ctx.decision.final_size = 0.0
            ctx.risk.evaluation.verdict = "rejected"
            ctx.risk.evaluation.reasons = reasons
        else:
            ctx.risk.evaluation.verdict = "approved"

        return ctx
