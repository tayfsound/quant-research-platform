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
            AgentDomain.RELATIVE_STRENGTH: self.adapter.to_relative_strength(ctx),
        }

        # Faz 268b — Regime-Aware Learning: PositionCloser._record_agent_
        # learning'in kapanmış işlemleri etiketlediği AYNI format
        # ("trend_volatility") — bu ikisi eşleşmezse regime-özel
        # snapshot'lar hiçbir zaman doğru anda seçilmez.
        features = ctx.market.features or {}
        trend = features.get("trend", "unknown")
        current_regime = f"{trend}_{features.get('volatility_regime', 'normal')}" if trend != "unknown" else None

        # Faz 268-sonrası — kullanıcı bulgusu: her ajan freshness'ı SABİT
        # bir varsayılanla bildiriyordu, gerçek veri yaşı hiç ölçülmüyordu.
        # deliberate()'e verilmeden ÖNCE hesaplanıyor — belief SENTEZİNDEN
        # önce uygulanmazsa (ör. deliberate() döndükten SONRA opinion.
        # freshness'ı değiştirmek) zaten hesaplanmış belief'i etkilemez.
        data_freshness = None
        last_bar_ts_raw = (ctx.market.raw_snapshot or {}).get("last_bar_timestamp")
        if last_bar_ts_raw:
            from datetime import UTC, datetime

            from market_data.features.signal_engine import compute_data_freshness

            try:
                last_bar_ts = datetime.fromisoformat(last_bar_ts_raw)
                data_freshness = compute_data_freshness(last_bar_ts, datetime.now(UTC), ctx.market.timeframe)
            except (ValueError, TypeError):
                data_freshness = None

        belief, opinions = self.orchestrator.deliberate(
            contexts, regime=current_regime, symbol=ctx.market.symbol or None,
            data_freshness=data_freshness,
        )

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
    # Faz 268-sonrası — kullanıcı isteği, gerçek örneklerle doğrulandı
    # (bkz. ADAUSDT %19.1 güven kararı: technical ajanı %87 güvenle VE
    # kalibrasyon modelinin x1.09 ile doğruladığı zengin kanıtla belief
    # yönünün TERSİNE işaret ederken sistem yine de LONG açmıştı —
    # ağırlıklı toplam oylama, tek başına çok güvenilir bir itirazı sayıca
    # fazla ama zayıf seslere karşı hiç ayrıcalıklı görmüyordu). Kullanıcının
    # kendi ifadesiyle: "İyi trade doğru zamanda doğru hamleyi yapmaktır,
    # zırt pırt pozisyon açmak değil."
    #
    # Faz 268-sonrası (2) — kullanıcı kararıyla 0.75'ten 0.65'e çekildi:
    # sistem genel olarak daha temkinli olsun, VE benched ajan eşiğinin
    # (aşağıda) altında kalarak mantık sırası korunsun (güvenilir/benched-
    # olmayan bir ajan için daha DÜŞÜK bar, benched bir ajan için biraz
    # daha YÜKSEK bar — "az güvenilen sesin ciddiye alınması için daha
    # sağlam bir sinyal gerekir" ilkesi tersine dönmesin).
    STRONG_DISSENT_CONFIDENCE_THRESHOLD = 0.65

    # Faz 268-sonrası — kullanıcı bulgusu, gerçek örnekle doğrulandı
    # (LDOUSDT: technical ajanı %89 güvenle SHORT diyordu — EMA'lar
    # düşüş yönlü, fiyat VWAP'ın %80 altında, gerçek somut kanıtla — ama
    # benched olduğu (son 20 kararının isabeti %20, eşiğin altında) için
    # effective_influence=0 idi ve strong-dissent kuralı onu HİÇ
    # saymıyordu; karar sadece macro'nun %74 güvenli tek sesiyle %84.4
    # nihai güvenle LONG açıldı). Kronik düşük isabet, HER tekil tahminin
    # yanlış olacağı anlamına gelmez — ama genel güvenilirliği düşük
    # olduğu için normal eşikten biraz daha YÜKSEK, daha sağlam bir
    # sinyal gerektiriyor. Benched bir ajan artık TAMAMEN yok sayılmıyor;
    # bu eşiği geçerse yine WAIT'e zorluyor.
    #
    # Kritik kalibrasyon düzeltmesi: ilk seçilen değer (0.90) TAM OLARAK
    # bu düzeltmeyi tetikleyen gerçek örneği (technical %89) YAKALAMIYORDU
    # — kullanıcı bunu hemen fark etti. Kullanıcı kararıyla 0.70'e
    # çekildi (sistem artık genel olarak daha temkinli, benched bir
    # ajanın bile orta-yüksek güvenli itirazını ciddiye alıyor).
    BENCHED_STRONG_DISSENT_CONFIDENCE_THRESHOLD = 0.70

    def __init__(self):
        self.metacognition = Metacognition()

    def execute(self, ctx: CognitiveCycleContext, belief: Belief, opinions: list[AgentOpinion]) -> CognitiveCycleContext:
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

        # Faz 268-sonrası — kullanıcı isteği: Faz 207'nin test-modu
        # tabanı (reduce_threshold'u 0.05'e indirme) KALDIRILDI. Kullanıcının
        # kendi gözlemi: "%19 ile bile pozisyon alıyor... confidence
        # değerinin önemi yok, 20 ile de 80 ile de pozisyona giriyorsa bu
        # veri bir anlam ifade etmiyor demektir." Faz 207'nin amacı hızlı
        # veri birikimiydi ama confidence'ı anlamsızlaştırarak bunu
        # yapıyordu — hem gerçek sonuçları öğrenme döngülerine (weight
        # optimizer, confidence kalibrasyonu) gürültü olarak besliyor hem
        # de "iyi trade doğru zamanda doğru hamledir" ilkesine aykırı
        # düşüyordu. Veri hacmi ihtiyacı artık watchlist genişletilerek
        # (daha fazla sembol) karşılanıyor — tek bir sembolde karar
        # kalitesinden ödün vermeye gerek kalmadı. Test modunda da artık
        # canlıyla AYNI reduce_threshold (act_threshold zaten hep aynıydı).

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

        # Güçlü tek-ses itirazı: benched OLMAYAN (effective_influence>0)
        # bir ajan normal eşiğin (0.75) üzerinde güvenle nihai yönün
        # TERSİNE işaret ediyorsa pozisyon açma. Benched bir ajan da
        # (effective_influence=0, kronik düşük isabet nedeniyle oyu
        # zaten sıfırlanmış) TAMAMEN yok sayılmıyor — çok daha yüksek
        # bir bar (0.90) geçerse o da WAIT'e zorluyor.
        strong_dissent = any(
            o.direction in ("LONG", "SHORT")
            and o.direction != belief.direction
            and (
                (o.effective_influence > 0 and o.confidence > self.STRONG_DISSENT_CONFIDENCE_THRESHOLD)
                or (o.effective_influence == 0 and o.confidence > self.BENCHED_STRONG_DISSENT_CONFIDENCE_THRESHOLD)
            )
            for o in opinions
        )
        #
        # NOT — "ince konsey" (az sayıda aktif ajan) için AYRI bir sabit
        # sayı eşiği KASITLI OLARAK eklenmedi: gerçek 23.221 kararlık
        # geçmiş veriyle ölçüldü, katılımcı sayısı ile confidence ZIT
        # yönde ilişkili çıktı (tek başına çelişkisiz bir ses confidence'ı
        # YAPAY OLARAK yükseltebiliyor — ort. 1 katılımcı: %50 confidence,
        # ort. 5 katılımcı: %35 — çünkü çok seslilikte anlaşmazlık zaten
        # kendiliğinden confidence'ı düşürüyor). Sabit bir "en az N ajan"
        # kuralı gerçek geçmiş kararların ~%64'ünü (aktif katılımcı<3)
        # ayrım gözetmeksizin bloke ederdi — kullanıcının "iki uç noktada
        # gidip geleceğiz" endişesi haklı, bu körü körüne kesim çözüm
        # değildi. Asıl düzeltme aşağıdaki reduce_threshold'un test
        # modunda da GERÇEK değerine dönmesi: hem "kumar" örneği (%16.9)
        # hem ADAUSDT örneği (%19.1) zaten SADECE bununla WAIT'e düşüyor
        # — ayrı bir katılımcı sayısı kuralına gerek kalmadan.
        if strong_dissent:
            meta["decision"] = "WAIT"

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


class PredictiveRiskStage:
    """Faz 244-246: Predictive Risk — Regime-Switching Monte Carlo + CPPI.

    MetaStage'in (Kelly) belirlediği final_size'ı, GERÇEK geçmiş rejim-
    koşullu getiri dağılımından bootstrap edilen bir Monte Carlo
    simülasyonunun tahmin ettiği "yakın vadeli seri kayıp" riskine göre
    EK olarak küçültür — RiskTargetStage'den (stop/target kurulumu)
    ÖNCE çalışır, mevcut statik risk kapılarının (RiskGateStage) yerine
    değil, onlara EK bir katman olarak. Yetersiz rejim verisi varsa
    (fail-closed) final_size hiç değişmez."""

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        if (ctx.decision.final_size or 0.0) <= 0:
            return ctx

        features = ctx.market.features or {}
        trend = features.get("trend", "unknown")
        if trend == "unknown":
            return ctx
        regime = f"{trend}_{features.get('volatility_regime', 'normal')}"

        from risk.predictive.cppi import cppi_exposure_multiplier
        from risk.predictive.monte_carlo import (
            load_regime_conditioned_pnl_pct,
            simulate_regime_drawdown_risk,
        )

        pct_returns = load_regime_conditioned_pnl_pct(regime)
        result = simulate_regime_drawdown_risk(pct_returns)
        multiplier = cppi_exposure_multiplier(result)

        ctx.cognition.relevant_knowledge.append({
            "type": "predictive_risk",
            "data": {
                "regime": regime,
                "sample_count": result.get("sample_count"),
                "breach_probability": result.get("breach_probability"),
                "exposure_multiplier": multiplier,
            },
        })

        if multiplier < 1.0:
            ctx.decision.final_size = round(ctx.decision.final_size * multiplier, 8)

        return ctx


class DrawdownSizingStage:
    """Faz 268-sonrası: Drawdown-Based Position Sizing (gambler's ruin
    koruması). Kill switch'in KULLANDIĞI AYNI gerçek ardışık kayıp
    sayacını (ctx.risk.consecutive_losses — services/risk_state.py'de
    zaten hesaplanmış, ikinci bir hesaplama yok), kill switch'in "hep ya
    da hiç" sert durmasından ÖNCE devreye giren kademeli bir fren olarak
    kullanır. MetaStage'in (Kelly) ve PredictiveRiskStage'in (CPPI) EK
    bir çarpanı — asla büyütmez, sadece küçültür."""

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        if (ctx.decision.final_size or 0.0) <= 0:
            return ctx

        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory
        from risk.drawdown_sizing import drawdown_size_multiplier

        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            start_after_losses = int(settings_repo.get("drawdown_sizing_start_after_losses"))
            full_reduction_at_losses = int(settings_repo.get("drawdown_sizing_full_reduction_at_losses"))

        multiplier = drawdown_size_multiplier(
            consecutive_losses=ctx.risk.consecutive_losses,
            start_after_losses=start_after_losses,
            full_reduction_at_losses=full_reduction_at_losses,
        )

        ctx.cognition.relevant_knowledge.append({
            "type": "drawdown_sizing",
            "data": {
                "consecutive_losses": ctx.risk.consecutive_losses,
                "exposure_multiplier": multiplier,
            },
        })

        if multiplier < 1.0:
            ctx.decision.final_size = round(ctx.decision.final_size * multiplier, 8)

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
    gerçek, temiz veriyle yeniden değerlendirilecek.

    Faz 268-sonrası — o yeniden değerlendirme yapıldı (bkz. app_settings_
    repository.py::DEFAULTS["target_atr_mult"] üstündeki not): gerçek OOS
    doğrulaması 1:4'ün tersini işaret etti (hedef, stop'tan KÜÇÜK olmalı).
    Sabit sınıf sabitleri yerine artık AppSettings'ten okunuyor — DSR henüz
    istatistiksel kanıt eşiğini geçmediği için (yön güçlü ama örneklem
    küçük) bu oranın redeploy gerektirmeden hızla ayarlanabilir kalması
    kasıtlı bir tasarım kararı."""
    DEFAULT_STOP_ATR_MULT = 2.5
    DEFAULT_TARGET_ATR_MULT = 1.4
    # Faz 268-sonrası — gerçek bulgu: kapanmış işlemleri "scalp" (stop <
    # %4.5, bkz. api/rest/positions.py::_SCALP_MAX_STOP_PCT) / gün_içi /
    # swing türüne göre ayırınca, scalp TEK BAŞINA toplam zararın %92'sini
    # oluşturuyordu (-$1954 / -$2129), diğer türlerin hepsi kârdaydı.
    # Mekanizma: düşük volatilite anlarında ATR-tabanlı stop doğal olarak
    # çok dar çıkıyor — dar stop, normal piyasa gürültüsüyle bile kolayca
    # tetikleniyor (Faz 251'deki AYNI mekanizma). MIN_STOP_PCT, hesaplanan
    # stop bu tabanın altına düşerse SL/TP'yi ORANI KORUYARAK genişletir
    # — asla daraltmaz, sadece "scalp" bölgesine hiç girilmesini engeller.
    DEFAULT_MIN_STOP_PCT = 0.045

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        direction = (ctx.decision.proposed_direction or "").upper()
        if direction not in ("LONG", "SHORT"):
            return ctx

        daily_atr_pct = (ctx.market.features or {}).get("daily_atr_pct")
        current_price = (ctx.market.raw_snapshot or {}).get("close")
        if not daily_atr_pct or daily_atr_pct <= 0 or not current_price or current_price <= 0:
            return ctx

        stop_mult, target_mult, min_stop_pct = self._load_multipliers()

        # Faz 268-sonrası — kullanıcı isteği: Adaptive Barrier Engine
        # (MAE/MFE'nin GERÇEK koşullu dağılımından türetilmiş SL/TP
        # önerisi) wire edildi. Varsayılan KAPALI (adaptive_barrier_
        # enabled) — açıldığında bile SADECE yeterli örneklemli, gerçek
        # bir kovaya düşen kararlar için devreye girer; aksi halde
        # (fail-closed) hemen altındaki, zaten doğrulanmış statik
        # ATR-tabanlı hesaba düşülür. Adaptive öneri de min_stop_pct
        # tabanından ASLA muaf değil — aynı güvenlik tabanı her iki
        # yoldan da geçerli.
        adaptive = self._try_adaptive_barrier(ctx)
        if adaptive is not None:
            stop_pct, target_pct = adaptive
        else:
            stop_pct = stop_mult * daily_atr_pct
            target_pct = target_mult * daily_atr_pct
        if stop_pct < min_stop_pct:
            scale = min_stop_pct / stop_pct
            stop_pct *= scale
            target_pct *= scale

        ctx.decision.stop_loss = current_price * stop_pct
        ctx.decision.take_profit = current_price * target_pct
        return ctx

    def _try_adaptive_barrier(self, ctx: CognitiveCycleContext) -> tuple[float, float] | None:
        """adaptive_barrier_enabled kapalıysa, kaydedilmiş bir tablo
        yoksa, ya da kararın düştüğü koşul kovası (yön/rejim/volatilite)
        için yeterli örneklemli/kararlı bir öneri yoksa None — çağıran
        taraf statik ATR hesabına düşer. Hiçbir hata burada yukarı
        fırlatılmaz (fail-closed, adaptive öneri asla zorunlu değil)."""
        try:
            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.session_factory import SessionFactory

            with SessionFactory.get_session() as session:
                enabled = AppSettingsRepository(session).get("adaptive_barrier_enabled") == "true"
            if not enabled:
                return None

            from analytics.adaptive_barrier_engine import recommend_barrier
            from analytics.barrier_table_repository import BarrierTableRepository

            stored = BarrierTableRepository().get_latest()
            if stored is None:
                return None

            features = ctx.market.features or {}
            context = {
                "direction": (ctx.decision.proposed_direction or "").upper(),
                "regime": features.get("long_term_trend_regime", "unknown"),
                "volatility_regime": features.get("volatility_regime", "unknown"),
                "confidence": ctx.decision.confidence or 0.0,
            }
            recommendation = recommend_barrier(context, stored["table"], group_by=tuple(stored["group_by"]))
            if recommendation is None:
                return None
            return recommendation["sl_pct"], recommendation["tp_pct"]
        except Exception:
            return None

    def _load_multipliers(self) -> tuple[float, float, float]:
        try:
            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.session_factory import SessionFactory

            with SessionFactory.get_session() as session:
                settings_repo = AppSettingsRepository(session)
                stop_mult = float(settings_repo.get("stop_atr_mult") or self.DEFAULT_STOP_ATR_MULT)
                target_mult = float(settings_repo.get("target_atr_mult") or self.DEFAULT_TARGET_ATR_MULT)
                min_stop_pct = float(settings_repo.get("min_stop_pct") or self.DEFAULT_MIN_STOP_PCT)
                return stop_mult, target_mult, min_stop_pct
        except Exception:
            return self.DEFAULT_STOP_ATR_MULT, self.DEFAULT_TARGET_ATR_MULT, self.DEFAULT_MIN_STOP_PCT


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
        experiment_bucket = None

        if hasattr(ctx, "cognition"):
            for item in ctx.cognition.relevant_knowledge:
                if item.get("type") == "decision_fusion":
                    decision_fusion_entries.append(item.get("data"))

            for item in reversed(ctx.cognition.relevant_knowledge):
                if item.get("type") == "debate_result":
                    debate_result = item.get("data")

                if item.get("type") == "weight_snapshot":
                    weight_snapshot_id = item.get("data", {}).get("id")

                if item.get("type") == "experiment_bucket" and experiment_bucket is None:
                    experiment_bucket = item.get("data", {}).get("bucket")

                if debate_result and weight_snapshot_id and experiment_bucket:
                    break

        event = self.recorder.record(
            ctx,
            opinions,
            belief,
            debate_result,
            weight_snapshot_id,
            decision_fusion_entries,
            experiment_bucket,
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

        # Faz 262 — kritik bulgu: bu "test modunda devre dışı" bypass'ı
        # RiskEngine.execute() (ön kapı) için kaldırılmıştı ("kasa %15.9'a,
        # 1074 açık pozisyona ulaşana kadar hiçbir kontrol devreye
        # girmedi" — bkz. o dosyadaki not) ama bu SON kapı (final_size/
        # concurrent-position/capital-% kontrolleri) gözden kaçmış,
        # AYNI bypass burada hâlâ duruyordu. Sistem trading_mode="test"
        # iken çalıştığı için bu, MAX_CONCURRENT_POSITIONS/MAX_CAPITAL_PCT
        # dahil TÜM post-fusion kontrollerinin baştan beri fiilen devre
        # dışı olduğu anlamına geliyordu — gerçek olay (2026-08-13):
        # XAUTUSDT'de 54 SHORT pozisyon aynı anda açık kalabilmişti.
        # Faz 262'nin kendi kararı ("test modu artık live modla AYNI
        # kuralları uyguluyor") burada da uygulanıyor.

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

        # Faz 268-sonrası — gerçek olay: XAUTUSDT'de aynı yönde (SHORT)
        # 54 pozisyon aynı anda açık kalabilmişti. max_concurrent_positions
        # TOPLAM sayıya bakıyor, ENB/Cross-Symbol Correlation Filter de
        # sadece aynı cycle'daki eşzamanlı önerilere bakıyor — hiçbiri
        # saatler içinde AYNI sembol/yönde BİRİKEN pozisyonu görmüyor.
        final_direction = "LONG" if ctx.decision.action == ActionType.ENTER_LONG else (
            "SHORT" if ctx.decision.action == ActionType.ENTER_SHORT else None
        )
        if (
            final_direction is not None
            and ctx.risk.max_open_positions_per_symbol_direction is not None
            and ctx.risk.max_open_positions_per_symbol_direction > 0
        ):
            existing = ctx.risk.same_direction_open_counts.get(final_direction, 0)
            if existing >= ctx.risk.max_open_positions_per_symbol_direction:
                reasons.append(RiskReason(
                    code="MAX_SAME_SYMBOL_DIRECTION_POSITIONS",
                    message=(
                        f"{existing} {final_direction} positions already open on this symbol "
                        f">= limit {ctx.risk.max_open_positions_per_symbol_direction}"
                    ),
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
