"""Cognitive Pipeline Aşamaları — opinions akışı + Debate hafızası + RecordingStage."""
import structlog

from agents.registry import AgentRegistry
from contracts.agent import AgentDomain, AgentOpinion
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from contracts.contexts.risk import RiskReason
from contracts.decision_event import DecisionEvent
from services.context_adapter import ContextAdapter
from services.council_orchestrator import CouncilOrchestrator
from services.decision_context_builder import DecisionContextBuilder
from services.decision_fusion import DecisionFusion
from services.decision_recorder import DecisionRecorder
from services.kelly_sizing import kelly_size_multiplier
from services.knowledge_base import KnowledgeBase
from services.metacognition import Metacognition

logger = structlog.get_logger()


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
            AgentDomain.ONCHAIN: self.adapter.to_onchain(ctx),
            AgentDomain.TECHNICAL: self.adapter.to_technical(ctx),
            AgentDomain.PATTERN: self.adapter.to_pattern(ctx),
            AgentDomain.QUANT: self.adapter.to_quant(ctx),
            AgentDomain.ORDER_FLOW: self.adapter.to_order_flow(ctx),
            AgentDomain.TIME: self.adapter.to_time(ctx),
            AgentDomain.EPISTEMOLOGY: self.adapter.to_epistemology(ctx),
            AgentDomain.RELATIVE_STRENGTH: self.adapter.to_relative_strength(ctx),
            AgentDomain.CREDIT: self.adapter.to_credit(ctx),
            AgentDomain.VOLATILITY: self.adapter.to_volatility(ctx),
            # Faz 367-devam — kullanıcı kararıyla geri getirildi (2026-08-28,
            # bkz. contracts/agent.py::VOTING_AGENT_DOMAINS üstündeki not).
            AgentDomain.SENTIMENT: self.adapter.to_sentiment(ctx),
        }

        # Kullanıcı bulgusu — bkz. contracts/contexts/market.py::
        # data_unavailable_domains docstring'i: gerçek veri kaynağı
        # olmayan domain'ler hiç çağrılmasın, kör bir WAIT üretip
        # BeliefEngine'in total_weight paydasını şişirmesin.
        for domain_value in ctx.market.data_unavailable_domains:
            for domain in list(contexts.keys()):
                if domain.value == domain_value:
                    contexts[domain] = None

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
            # Faz 362-devam — self_reliability_gate_enabled'ı AYRI bir
            # session'la (aşağıda) DEĞİL burada, zaten açık olan session'la
            # okuyoruz — cascade artık HER sembol için ~3 kat MetaStage.
            # execute() çağırdığından (150 sembol × 3 = ~450/cycle), her
            # çağrıda YENİ bir DB session açmak gerçek bir yavaşlamaya/
            # bağlantı havuzu baskısına yol açtı (canlıda gözlemlendi: bir
            # cycle 6+ dakika sürüp kilitlendi).
            self_reliability_gate_enabled = settings_repo.get("self_reliability_gate_enabled") == "true"

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
        # bir ajan normal eşiğin (STRONG_DISSENT_CONFIDENCE_THRESHOLD,
        # şu an 0.65 — bkz. yukarıdaki tanım ve Faz 268-sonrası'ndaki
        # 0.75->0.65 değişikliği) üzerinde güvenle nihai yönün TERSİNE
        # işaret ediyorsa pozisyon açma. Benched bir ajan da
        # (effective_influence=0, kronik düşük isabet nedeniyle oyu
        # zaten sıfırlanmış) TAMAMEN yok sayılmıyor — çok daha yüksek bir
        # bar (BENCHED_STRONG_DISSENT_CONFIDENCE_THRESHOLD, şu an 0.70)
        # geçerse o da WAIT'e zorluyor. (2026-08-24: bu yorum bloğundaki
        # eski 0.75/0.90 rakamları, aşağıdaki tanımlarla çelişen bir
        # driftti — güncellendi.)
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

        # Yatay piyasa gate'i — kullanıcı isteği: kısa vadeli trend gücü
        # (ADX) DÜŞÜK ve uzun vadeli rejim (200-EMA tabanlı) belirsizken
        # (transition — ne bull ne bear, insufficient_data DEĞİL) pozisyon
        # açma. Gerçek 2990 kararlık geçmiş veriyle doğrulandı: bu ikisi
        # AYNI ANDA sadece %2.4 oranında oluşuyor — önceden reddedilen
        # "min katılımcı" gate'i gibi tarihin büyük bir kısmını körü
        # körüne bloke eden geniş bir kesim DEĞİL, gerçekten nadir ve
        # anlamlı bir "piyasada ne kısa ne uzun vadede net bir yön var"
        # durumu.
        #
        # Faz 293 — dış rapor önerisi (kullanıcı doğrulattı): "tek sinyale
        # bağlı filtre hem false positive hem false negative üretebilir,
        # Hurst ~0.5 bandı + Bollinger bandwidth sıkışması ikinci/üçüncü
        # teyit olarak eklenebilir." Gerçek 4949 kararlık veriyle test
        # edildi: Hurst [0.45,0.55] TEK BAŞINA %76 oranında true çıkıyor
        # (kripto kısa pencerede neredeyse hep rastgele-yürüyüşe yakın —
        # tek başına ayırt edici değil, "2'den fazlası true" gibi bir oy
        # kuralına eklenince gate %1.4'ten %41.5'e fırlıyor, tarihin
        # neredeyse yarısını körü körüne bloke ediyor — TAM olarak
        # reddedilen "min katılımcı" hatasının tekrarı). Hurst dead-zone'u
        # SADECE aynı anda GERÇEKTEN sıkışmış bir Bollinger bandwidth'le
        # (<0.03 — aynı 4949 kararlık gerçek dağılımda alt %0.5'lik dilim,
        # rastgele bir yuvarlak sayı değil) birleştirince ayrı, dar ve
        # anlamlı bir ikinci yol oluşuyor: toplam gate oranı %1.4'ten
        # %1.9'a çıkıyor — gerçekten yeni chop örnekleri yakalıyor,
        # tarihi indiscriminate bloklamıyor.
        features = ctx.market.features or {}
        adx = features.get("adx")
        long_term_trend_regime = features.get("long_term_trend_regime")
        weak_adx_transition = adx is not None and adx < 20 and long_term_trend_regime == "transition"

        hurst_exponent = features.get("hurst_exponent")
        bollinger_bandwidth = features.get("bollinger_bandwidth")
        hurst_dead_zone = hurst_exponent is not None and 0.45 <= hurst_exponent <= 0.55
        extreme_bollinger_squeeze = bollinger_bandwidth is not None and bollinger_bandwidth < 0.03

        sideways_market = weak_adx_transition or (hurst_dead_zone and extreme_bollinger_squeeze)
        if sideways_market:
            meta["decision"] = "WAIT"

        # Faz 342 — kullanıcı isteği: "short pozisyonlar neden karlı
        # değil?" Gerçek 1577 kapanmış kararla ölçüldü: council'in kendi
        # SHORT kararları genel olarak %21.6 isabetli (LONG %96.4) —
        # ama bu SADECE bir rejimden kaynaklanıyor. market_regime =
        # trend_volatility (bkz. position_closer.py::_extract_market_
        # regime, AYNI ctx.market.features) kırılımında: SHORT/bearish/
        # low n=424, isabet SADECE %8.3 (toplam -$604) — LONG/bearish/low
        # n=398, isabet %95.2 (+$141). "bearish_low" (EMA20<EMA50 + düşük
        # gerçekleşen volatilite) fiilen bir DÜŞÜŞ DEVAMI değil, klasik
        # bir taban/konsolidasyon kurulumu — SHORT açmak dönüşe karşı
        # bahis oluyor. Bu, pump_fade'in Faz 327/332/341'de zaten
        # düzelttiği "bearish ≠ SHORT-favorable" hatasının council
        # seviyesindeki karşılığı. "Sadece sıkılaştır" ilkesiyle: SADECE
        # bu spesifik (yön=SHORT + trend=bearish + volatilite=low)
        # kombinasyonunda WAIT'e zorlanıyor — LONG'a, diğer rejimlere ya
        # da diğer volatilite seviyelerindeki bearish SHORT'lara (n=47
        # normal %46.8, n=11 high %90.9 — ikisi de bearish_low'dan çok
        # daha iyi) hiç dokunulmuyor.
        trend = features.get("trend")
        volatility_regime = features.get("volatility_regime")
        short_in_bearish_low = (
            belief.direction == "SHORT" and trend == "bearish" and volatility_regime == "low"
        )
        if short_in_bearish_low:
            meta["decision"] = "WAIT"

        # Faz 352 — Regime Reversal Guardian (kullanıcı fikri, GERÇEK bir
        # olayla doğrulandı: LONG'da art arda 14 stop-loss, 275 açık
        # LONG'un 170'i zararda). belief.direction'da son N kapanışta
        # ardışık stop-loss sayısı eşiği aşarsa (bkz. services/regime_
        # reversal_guardian.py — stateless, her cycle taze hesaplanır, bir
        # kazanç gelince kendi kendine kalkar) o yönde YENİ pozisyon
        # açılmıyor — kill switch'in GLOBAL/kalıcı durdurmasından farklı,
        # SADECE bu yönü, SADECE streak kırılana kadar etkiler. Mevcut
        # açık pozisyonların defansif kapatılması ayrı bir periyodik görev
        # (regime_reversal_guardian_task), burada SADECE yön kararı.
        if belief.direction in ("LONG", "SHORT") and meta["decision"] == "ACT":
            try:
                from services.regime_reversal_guardian import is_direction_paused

                if is_direction_paused(belief.direction):
                    meta["decision"] = "WAIT"
            except Exception as exc:
                structlog.get_logger().warning("regime_reversal_gate_failed", error=str(exc))

        # Faz 297 — dış rapor önerisi (kullanıcı doğrulattı): "yüksek
        # entropy/düşük konsensüste action eşiğinin otomatik yükselmesi."
        # belief.entropy (services/belief_engine.py::synthesize'ın 3 yönlü
        # — LONG/SHORT/WAIT — Shannon entropisi) HİÇBİR YERDE
        # kullanılmıyordu; conflict_level SADECE belief.uncertainty'yi
        # (2 yönlü, en güçlü ikinci sesin oranı) kullanıyordu. Gerçek
        # kararlar tarihsel olarak entropy DEĞERİNİ saklamıyordu (sadece
        # ajan oylarını) — bu yüzden 1058 gerçek karar, services/
        # belief_engine.py::synthesize'ın AYNI pure fonksiyonuyla
        # (analytics/agent_ablation.py::reconstruct_opinions ile AYNI
        # rekonstrüksiyon) yeniden hesaplanıp entropy dağılımı ölçüldü:
        # entropy>=1.5 (dağılımın gerçek üst %11'i, teorik tavana —
        # log2(3)≈1.585 — yakın, "gerçekten maksimuma yakın anlaşmazlık"),
        # 544 kapanmış kararda ORTALAMA pnl ~2.4 kat daha kötüydü (-1.71
        # vs -0.72), win_rate'te büyük fark YOKTU (%31 vs %28) — yani
        # yüksek entropy işlemi engellemiyor, kaybedince DAHA BÜYÜK
        # kaybettiriyor. Eşik birkaç komşu değerde (1.4-1.55) tutarlıydı,
        # tek bir nokta tesadüfü değil. Bu yüzden WAIT'e değil (kanıt tam
        # blok için yeterince güçlü değil) REDUCE'a zorluyor — boyut
        # küçülsün, fırsat tamamen kapanmasın.
        if belief.entropy >= 1.5 and meta["decision"] == "ACT":
            meta["decision"] = "REDUCE"

        # Faz 310 — kullanıcı isteği: "self modeli karar hattına
        # bağlayalım." Self-Model (services/self_model_gatherer.py) şu ana
        # kadar SADECE dashboard raporuydu — sistem "kendine ne kadar
        # güvendiğini" biliyordu ama bu bilgiyi kararlarında hiç
        # kullanmıyordu (3. dış rapor bulgusu, kullanıcı doğrulattı).
        #
        # kill_switch_active ve concept_drift_detected BİLEREK burada
        # TEKRAR kontrol edilmiyor — ilki zaten ctx.risk.ai_enabled'ı
        # kalıcı olarak false'a çekip RiskGateStage'de reddediyor
        # (engines/risk_engine.py), ikincisi zaten ctx.risk.concept_drift_
        # reason ile ayrı bir RiskReason olarak enforce ediliyor — burada
        # da tekrarlamak çift cezalandırma olurdu. Bu gate'in kattığı
        # GERÇEKTEN yeni bilgi: recent_dsr (istatistiksel beceri güveni)
        # ve ece (kalibrasyon kalitesi) — ikisi de şu ana kadar hiçbir
        # yerde canlı kararı etkilemiyordu.
        #
        # Faz 362-devam — kullanıcı bulgusu (2026-08-25, gerçek olay):
        # recent_dsr, son 500 kapanmış işlemin GERÇEKTEN negatif Sharpe
        # oranı (-0.073, %75 win rate'e rağmen — n_trials şişmesi değil,
        # doğrulandı: n_trials=1'de bile DSR≈0) yüzünden 0.0'a düşüp
        # eşiği (0.3) geçti — sistem SAATLERCE hiç pozisyon açmadı. Ölçüm
        # doğru, mekanizma tasarım gereği çalışıyor — ama test modunda
        # (henüz üretim/canlı sermaye değil) veri birikimini tamamen
        # durdurmak istenmiyor. `self_reliability_gate_enabled` ile
        # devre dışı bırakılabiliyor — trading_mode="live" olduğunda
        # kullanıcı bunu SEÇEREK açık tutmalı (varsayılan true).
        # (Değer execute()'ın en başındaki tek DB session'ında okundu.)
        if self_reliability_gate_enabled:
            try:
                from analytics.self_model import (
                    DEGRADED_DSR_THRESHOLD,
                    POOR_CALIBRATION_ECE_THRESHOLD,
                    UNTRUSTWORTHY_DSR_THRESHOLD,
                )
                from services.self_model_gatherer import get_cached_self_reliability_snapshot

                self_reliability_inputs = get_cached_self_reliability_snapshot()["inputs"]
                recent_dsr = self_reliability_inputs.get("recent_dsr")
                ece = self_reliability_inputs.get("ece")

                if recent_dsr is not None and recent_dsr < UNTRUSTWORTHY_DSR_THRESHOLD:
                    meta["decision"] = "WAIT"
                elif meta["decision"] == "ACT" and (
                    (recent_dsr is not None and recent_dsr < DEGRADED_DSR_THRESHOLD)
                    or (ece is not None and ece > POOR_CALIBRATION_ECE_THRESHOLD)
                ):
                    meta["decision"] = "REDUCE"
            except Exception as exc:
                structlog.get_logger().warning("self_reliability_gate_failed", error=str(exc))

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
            #
            # Faz 290: rejim de veriliyor — services/position_closer.py::
            # _extract_market_regime ile AYNI "trend_volatility" formatı
            # (regime-özel kovaların açılış/kapanış tarafında birebir
            # eşleşmesi bunun aynı olmasına bağlı). trend "unknown"sa
            # (gerçek market_snapshot yoksa) None veriliyor — kelly_
            # sizing zaten bu durumda confidence-only davranışına düşüyor.
            trend = features.get("trend", "unknown")
            regime = f"{trend}_{features.get('volatility_regime', 'normal')}" if trend != "unknown" else None
            kelly_multiplier = kelly_size_multiplier(meta["confidence"], regime=regime)
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


class SelfCorrectionSizingStage:
    """Faz 368 — kullanıcı kararı (2026-08-28, Grok raporu doğrulaması):
    scientific_self_correction'ın "bu yönün hipotezi hâlâ geçerli mi?"
    sorusunu (services/scientific_self_correction_gatherer.py) pozisyon
    boyutuna bağlar. DrawdownSizingStage ile AYNI "asla büyütmez, sadece
    küçültür" ilkesi — o ardışık kayba tepki verirken, bu YÖNÜN kendi
    istatistiksel geçmişinin son dönemde çöküp çökmediğine tepki verir.
    Kararı asla ENGELLEMEZ (LONG kaldırmayalım kararı — direction_
    trading_gate ayrı, kullanıcının manuel anahtarı), sadece boyutu
    orantılı küçültür. Veri kaynağı GÜNLÜK bir dosya-tabanlı anlık
    görüntü (analytics/self_correction_sizing_repository.py) — barrier
    table ile AYNI desen, her kararda ~3500 satırlık bir SQL taraması
    tekrarlanmıyor."""

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        if (ctx.decision.final_size or 0.0) <= 0:
            return ctx

        direction = (ctx.decision.proposed_direction or "").upper()
        if direction not in ("LONG", "SHORT"):
            return ctx

        from analytics.self_correction_sizing_gate import self_correction_size_multiplier
        from analytics.self_correction_sizing_repository import SelfCorrectionSizingRepository

        stored = SelfCorrectionSizingRepository().get_latest()
        segment = (stored or {}).get("segments", {}).get(f"direction={direction}")
        multiplier = self_correction_size_multiplier(segment)

        if multiplier < 1.0:
            ctx.cognition.relevant_knowledge.append({
                "type": "self_correction_sizing",
                "data": {
                    "direction": direction,
                    "exposure_multiplier": multiplier,
                    "original_win_rate": (segment or {}).get("original_win_rate"),
                    "recent_win_rate": (segment or {}).get("recent_win_rate"),
                },
            })
            ctx.decision.final_size = round(ctx.decision.final_size * multiplier, 8)

        return ctx


class SelfModelSizingStage:
    """Faz 368 — kullanıcı bulgusu (2026-08-28): "Kill Switch aktif olduğu
    halde self control kapalı gibi görünüyor" — Self-Model'in overall_
    reliability'si ("high"/"degraded"/"untrustworthy") hiçbir trading
    kararına bağlı DEĞİLDİ, sadece dashboard'da gösteriliyordu (bkz.
    analytics/self_model_sizing_gate.py'nin notu). Gerçek sert kill switch
    zaten ayrı çalışıyor (engines/risk_engine.py); bu stage Self-Model'in
    DAHA YUMUŞAK "degraded" sinyalini boyuta bağlıyor. Veri kaynağı
    self_model_snapshots tablosu (services/tasks.py::refresh_self_model_
    report_task, artık GÜNLÜK — DrawdownSizingStage'in aksine gather_self_
    reliability_snapshot() ~1.4sn sürüyor, sembol başına tekrar tekrar
    çağrılamaz, barrier table/self-correction sizing ile AYNI 'periyodik
    hesapla, kaydet, karar anında sadece oku' deseni)."""

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        if (ctx.decision.final_size or 0.0) <= 0:
            return ctx

        from analytics.self_model_sizing_gate import self_model_size_multiplier
        from database.repositories.self_model_report_repository import SelfModelReportRepository
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            stored = SelfModelReportRepository(session).get_latest()
        overall_reliability = (stored or {}).get("result", {}).get("overall_reliability")
        multiplier = self_model_size_multiplier(overall_reliability)

        if multiplier < 1.0:
            ctx.cognition.relevant_knowledge.append({
                "type": "self_model_sizing",
                "data": {
                    "overall_reliability": overall_reliability,
                    "exposure_multiplier": multiplier,
                },
            })
            ctx.decision.final_size = round(ctx.decision.final_size * multiplier, 8)

        return ctx


class PivotalAgentSizingStage:
    """Faz 368 — kullanıcı bulgusu (Grok raporu doğrulaması, agent_
    ablation.py'nin GERÇEK karşı-olgusal verisi): technical ajanı pivot
    olduğunda (oyu OLMASAYDI bu karar hiç açılmaz/farklı yöne açılırdı)
    kazanma oranı %25.4 (n=63) — genel ortalamanın çok altında; order_
    flow/macro ise pivot olunca TAM TERSİNE çok güçlü. Bu stage HERHANGİ
    bir domain'i hardcode ETMİYOR (bkz. analytics/pivotal_agent_sizing_
    gate.py'nin notu) — haftalık ablation raporundan 'pivot-olunca-kötü'
    domain'leri okuyup, O ANKİ kararda GERÇEKTEN pivot olup olmadığını
    (agent_ablation.py::synthesize_with_domain_excluded ile CANLI, ucuz
    bir yeniden-sentez — DB sorgusu yok) test eder. Birden fazla riskli
    domain pivotsa EN KÖTÜ (en düşük) çarpan uygulanır — 'iyi bir domain
    de vardı' bahanesiyle kötü bir domain görmezden gelinmez (agent_
    combination_reliability_gate.py ile AYNI ilke)."""

    def execute(self, ctx: CognitiveCycleContext, opinions: list | None = None) -> CognitiveCycleContext:
        if (ctx.decision.final_size or 0.0) <= 0 or not opinions:
            return ctx

        direction = (ctx.decision.proposed_direction or "").upper()
        if direction not in ("LONG", "SHORT"):
            return ctx

        from analytics.agent_ablation import synthesize_with_domain_excluded
        from analytics.pivotal_agent_sizing_gate import (
            identify_risky_pivotal_domains,
            pivotal_domain_size_multiplier,
        )
        from database.repositories.agent_ablation_report_repository import AgentAblationReportRepository
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            baseline_win_rate = float(settings_repo.get("agent_combination_gate_min_win_rate"))
            stored = AgentAblationReportRepository(session).get_latest()
        by_domain = (stored or {}).get("result", {}).get("by_domain", {})
        risky_domains = identify_risky_pivotal_domains(by_domain, baseline_win_rate)
        if not risky_domains:
            return ctx

        opinion_domains = {o.domain.value for o in opinions if o.direction == direction}

        worst_multiplier = 1.0
        worst_domain = None
        for domain, win_rate in risky_domains.items():
            if domain not in opinion_domains:
                continue
            counterfactual = synthesize_with_domain_excluded(opinions, domain)
            if counterfactual is None or counterfactual.direction == direction:
                continue  # bu kararda gerçekten pivot DEĞİL — o olmasa da aynı yön çıkardı
            multiplier = pivotal_domain_size_multiplier(win_rate, baseline_win_rate)
            if multiplier < worst_multiplier:
                worst_multiplier = multiplier
                worst_domain = domain

        if worst_multiplier < 1.0:
            ctx.cognition.relevant_knowledge.append({
                "type": "pivotal_agent_sizing",
                "data": {
                    "pivotal_domain": worst_domain,
                    "caused_trade_win_rate": risky_domains.get(worst_domain),
                    "exposure_multiplier": worst_multiplier,
                },
            })
            ctx.decision.final_size = round(ctx.decision.final_size * worst_multiplier, 8)

        return ctx


class SymbolPerformanceSizingStage:
    """Faz 368 — kullanıcı bulgusu (Grok raporu doğrulaması): council SL
    zararları belirli sembol×yön hücrelerinde sistematik olarak
    yoğunlaşıyor (ör. ATOMUSDT_LONG n=41, %31.7 kazanma, -$38.2k). Kara
    liste DEĞİL (kullanıcı kararı, LONG/SHORT anahtarındaki AYNI tercih:
    "kısıtlamayalım, boyut küçültelim") — analytics/symbol_performance_
    sizing_gate.py ile AYNI orantılı 'asla büyütmez, sadece küçültür'
    ailesi. Veri kaynağı günlük dosya-tabanlı anlık görüntü (analytics/
    symbol_performance_sizing_repository.py — barrier table/self-
    correction sizing ile AYNI desen)."""

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        if (ctx.decision.final_size or 0.0) <= 0:
            return ctx

        direction = (ctx.decision.proposed_direction or "").upper()
        if direction not in ("LONG", "SHORT") or not ctx.market.symbol:
            return ctx

        from analytics.symbol_performance_sizing_gate import symbol_direction_size_multiplier
        from analytics.symbol_performance_sizing_repository import SymbolPerformanceSizingRepository
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            baseline_win_rate = float(AppSettingsRepository(session).get("agent_combination_gate_min_win_rate"))

        stored = SymbolPerformanceSizingRepository().get_latest()
        key = f"{ctx.market.symbol}_{direction}"
        entry = (stored or {}).get("by_symbol_direction", {}).get(key)
        multiplier = symbol_direction_size_multiplier(
            (entry or {}).get("win_rate"), (entry or {}).get("sample_size"), baseline_win_rate,
        )

        if multiplier < 1.0:
            ctx.cognition.relevant_knowledge.append({
                "type": "symbol_performance_sizing",
                "data": {
                    "symbol_direction": key,
                    "win_rate": (entry or {}).get("win_rate"),
                    "sample_size": (entry or {}).get("sample_size"),
                    "exposure_multiplier": multiplier,
                },
            })
            ctx.decision.final_size = round(ctx.decision.final_size * multiplier, 8)

        return ctx


class RiskTargetStage:
    """Faz 191 — gerçek bulgu: DecisionFusion (aşağıda) `ctx.decision.
    take_profit_distance`/`stop_loss_distance`'a bakıp Expected Value hesaplıyordu, ama
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
    kasıtlı bir tasarım kararı.

    Faz 320 — kullanıcı isteği: "duraklattığımız Otomatik R/R kalibrasyonu
    işinin parçası olan target_atr_mult/stop_atr_mult oranının gerçek
    veriyle yeniden kalibre edilmesi." compute_optimal_barrier() gerçek
    orta-vadeli (4h/1d) kapanmış işlem MAE/MFE'siyle (1098 örneklem)
    çalıştırıldı — GÜÇLÜ bir yön asimetrisi bulundu: LONG'da empirik
    hedef/stop oranı ~2.75 (stop %3.30, hedef %9.09, EV +%5.85 — hedefler
    şu ana kadar ÇOK ERKEN kesiliyormuş), SHORT'ta ise en iyi ampirik
    ayarda bile EV NEGATİF (-%2.46, hedef ~%0 — bu vadede SHORT'un gerçek
    bir kenarı yok, R:R ayarıyla düzelmiyor). Kullanıcı kararıyla (Ask
    UserQuestion): tek global orandan yön-bazlı iki ayrı orana geçildi.
    LONG'da AYNI "stop sabit, hedef empirik oranla ölçeklenir" yöntemi
    (bkz. app_settings_repository.py::DEFAULTS) uygulandı: 2.5 * 2.7548 ≈
    6.89. SHORT bilinçli olarak ESKİ değerinde (1.4) bırakıldı — negatif
    EV'den türeyen bir oranı doğrudan uygulamak anlamsız bir "neredeyse
    anında kâr al" hedefi üretirdi; SHORT'un kendisi ayrı bir inceleme
    konusu (kalıcı bir düzeltme değil, gerçek kanıt eşiği geçilmeden hiçbir
    kalıcı değişiklik yapılmıyor ilkesiyle tutarlı).

    Faz 368 — kullanıcı kararı (2026-08-28, canlı olay): barrier tablosu
    artık SIFIR SHORT kovası üretiyor (bkz. analytics/mae_mfe.py::
    MIN_DISTINCT_DAYS notu — SHORT/bear_trend geçmişi neredeyse tamamen
    tek bir 3 günlük ters-yön rallisinden geliyordu), yani HER SHORT kararı
    bu statik orana düşüyor. 1.4 ~%64.1 breakeven confidence istiyordu —
    kullanıcı bunu geçici olarak 1.8'e gevşetmeyi seçti (~%58.1 breakeven,
    2.5/(1.8+2.5)) — daha fazla GERÇEK SHORT denemesi biriksin diye (n=20
    şu an istatistiksel olarak hiçbir şey kanıtlamıyor). Kalıcı bir "SHORT
    düzeldi" iddiası DEĞİL — sadece örneklem biriktirme kapısı biraz
    aralandı, scientific_self_correction SHORT hipotezi hâlâ 'geçerli'
    (kötü) diyor."""
    DEFAULT_STOP_ATR_MULT_LONG = 2.5
    DEFAULT_TARGET_ATR_MULT_LONG = 6.89
    DEFAULT_STOP_ATR_MULT_SHORT = 2.5
    DEFAULT_TARGET_ATR_MULT_SHORT = 1.8
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

    def execute(self, ctx: CognitiveCycleContext, opinions: list | None = None) -> CognitiveCycleContext:
        # 3. taraf inceleme bulgusu — gerçek: PredictiveRiskStage ve
        # DrawdownSizingStage final_size<=0 (MetaStage WAIT dediğinde,
        # ör. strong_dissent/sideways_market gate'i) ise hemen çıkıyordu
        # ama burası SADECE proposed_direction'a bakıyordu — belief.
        # direction (MetaStage'in WAIT dese bile HER ZAMAN set ettiği,
        # bkz. MetaStage.execute() sonundaki ctx.decision.proposed_
        # direction = belief.direction) LONG/SHORT olduğu her WAIT
        # kararında, sonucu zaten kullanılmayacak stop/target için 2
        # gereksiz DB sorgusu (_load_multipliers + _try_adaptive_barrier)
        # çalışıyordu — watchlist'teki her sembol her cycle'da genelde
        # WAIT olduğu için bu, gerçek bir tekrarlayan israf.
        if (ctx.decision.final_size or 0.0) <= 0:
            return ctx

        direction = (ctx.decision.proposed_direction or "").upper()
        if direction not in ("LONG", "SHORT"):
            return ctx

        daily_atr_pct = (ctx.market.features or {}).get("daily_atr_pct")
        current_price = (ctx.market.raw_snapshot or {}).get("close")
        if not daily_atr_pct or daily_atr_pct <= 0 or not current_price or current_price <= 0:
            return ctx

        stop_mult, target_mult, min_stop_pct = self._load_multipliers(direction)

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

        # Faz 299-300 — kullanıcı isteği: TP/SL Confluence canlıya bağlandı
        # ("wire edelim"). Faz 312'de Bollinger + Fibonacci de eklendi
        # (planlanmış ama unutulmuştu). Ölçüm katmanında doğrulandı:
        # ATR-tabanlı hedef gerçek yapısal seviyelere (S/R + Volume
        # Profile + Pivot + Donchian + Keltner + Bollinger + Fibonacci
        # "zone of agreement") SADECE %2-26 oranında
        # yakın düşüyor. Fiyat ile ATR hedefi ARASINDA (yani hedefe
        # ulaşmadan ÖNCE karşılaşılacak) en az 2 bağımsız yöntemin
        # birleştiği gerçek bir bölge varsa, hedef o bölgenin hemen önüne
        # çekiliyor — daha erken, gerçekçi bir kâr alımı. SADECE
        # sıkılaştırıyor (hedefi her zaman fiyata daha YAKIN bir noktaya
        # çeker, asla daha uzağa taşımaz — Kelly/CPPI/trailing stop ile
        # AYNI ilke). Uygun bir bölge yoksa (fail-closed) davranış hiç
        # değişmez.
        #
        # Faz 317-sonrası — kullanıcı bulgusu: "SL'de de faydalı olmaz
        # mıydı o veri?" Haklı — AYNI confluence bölgeleri artık stop için
        # de kullanılıyor (bkz. snap_stop_to_confluence docstring'i).
        # Stop-tarafı GÜVENLİ, çünkü aday bölgeler TANIM GEREĞİ fiyat İLE
        # mevcut ATR-stop ARASINDA kalıyor — hangi bölge seçilirse
        # seçilsin sonuç asla mevcut ATR-stop'tan DAHA UZAĞA gidemez,
        # riski ASLA artırmaz.
        confluence_zones = (ctx.market.features or {}).get("confluence_zones") or []
        if confluence_zones:
            from analytics.tp_sl_confluence import snap_stop_to_confluence, snap_target_to_confluence

            raw_target_price = (
                current_price * (1 + target_pct) if direction == "LONG"
                else current_price * (1 - target_pct)
            )
            adjusted_target_price, used_target_zone = snap_target_to_confluence(
                direction, current_price, raw_target_price, confluence_zones
            )
            if used_target_zone is not None:
                target_pct = abs(adjusted_target_price - current_price) / current_price
                ctx.cognition.relevant_knowledge.append({
                    "type": "tp_sl_confluence",
                    "data": {"zone": used_target_zone, "adjusted_target_pct": round(target_pct, 6)},
                })

            raw_stop_price = (
                current_price * (1 - stop_pct) if direction == "LONG"
                else current_price * (1 + stop_pct)
            )
            adjusted_stop_price, used_stop_zone = snap_stop_to_confluence(
                direction, current_price, raw_stop_price, confluence_zones
            )
            if used_stop_zone is not None:
                # min_stop_pct tabanı (Faz 268-sonrası — "scalp bölgesi"
                # gerçek olayı: TEK BAŞINA toplam zararın %92'sini
                # oluşturmuştu, bkz. yukarıdaki sınıf yorumu) confluence'tan
                # da MUAF DEĞİL — gerçek bir yapısal seviye bile olsa,
                # stop bu tabanın altına asla inmiyor.
                stop_pct = max(abs(adjusted_stop_price - current_price) / current_price, min_stop_pct)
                ctx.cognition.relevant_knowledge.append({
                    "type": "sl_confluence",
                    "data": {"zone": used_stop_zone, "adjusted_stop_pct": round(stop_pct, 6)},
                })

        ctx.decision.stop_loss_distance = current_price * stop_pct
        ctx.decision.take_profit_distance = current_price * target_pct

        # Faz 348 — kullanıcı onayı: Meta-Label Model (services/meta_
        # label_model.py) gerçek OOS kanıtını (test_accuracy %84.5 vs
        # taban %61.2, AUC 0.92, n=877) geçince bağlandı — SADECE
        # pozisyon boyutu çarpanı, yön kararı hiç etkilenmiyor. Henüz
        # eğitilmiş bir model yoksa (fail-closed None) hiçbir şey
        # değişmez, mevcut davranış aynen korunur.
        try:
            from analytics.opportunity_quality import agreement_from_opinions
            from services.decision_fusion import compute_fused_confidence
            from services.meta_label_model import meta_label_size_multiplier, predict_tp_probability

            features = dict(ctx.market.features or {})
            # Faz 363 — kullanıcı bulgusu: burada DAHA ÖNCE ctx.decision.
            # confidence doğrudan okunuyordu — pipeline'da bu aşama
            # DecisionFusion'dan ÖNCE çalıştığı için (bkz. cognitive_
            # engine.py::run sırası) bu HAM, kalibrasyon/opportunity-
            # quality-indirimi/InnerCritic çarpanı UYGULANMAMIŞ bir
            # değerdi. Ama modelin eğitim verisi (decisions.confidence,
            # bkz. meta_label_model.py::_extract_meta_label_training_rows)
            # DecisionFusion SONRASI, yani bu üçünü de görmüş NİHAİ
            # değerdi — train/serve tutarsızlığı. Artık AYNI hesabı
            # (compute_fused_confidence, yan etkisiz) burada da
            # çalıştırıyoruz, eğitim ve çalışma zamanı artık aynı anlamdaki
            # confidence'ı görüyor.
            features["confidence"] = compute_fused_confidence(ctx, opinions=opinions)
            features["planned_rr_ratio"] = (target_pct / stop_pct) if stop_pct > 0 else 0.0
            agreement = agreement_from_opinions(opinions)
            features["agent_agreement"] = agreement if agreement is not None else 0.0
            tp_probability = predict_tp_probability(features)
            if tp_probability is not None and ctx.decision.final_size > 0:
                multiplier = meta_label_size_multiplier(tp_probability)
                if multiplier < 1.0:
                    ctx.decision.final_size = round(ctx.decision.final_size * multiplier, 8)
                ctx.cognition.relevant_knowledge.append({
                    "type": "meta_label_sizing",
                    "data": {"tp_probability": tp_probability, "size_multiplier": multiplier},
                })
        except Exception as exc:
            structlog.get_logger().warning("meta_label_sizing_failed", error=str(exc))

        return ctx

    def _try_adaptive_barrier(self, ctx: CognitiveCycleContext) -> tuple[float, float] | None:
        """adaptive_barrier_enabled kapalıysa, kaydedilmiş bir tablo
        yoksa, ya da kararın düştüğü koşul kovası (yön/rejim/volatilite)
        için yeterli örneklemli/kararlı bir öneri yoksa None — çağıran
        taraf statik ATR hesabına düşer. Hiçbir hata burada yukarı
        fırlatılmaz (fail-closed, adaptive öneri asla zorunlu değil).

        Faz 269-sonrası — 3. taraf inceleme bulgusu: adaptive_barrier_
        enabled varsayılan AÇIK olduğu için, barrier tablosu ilk kez
        dolduğu an sistem hiç karşılaştırma fırsatı olmadan %100
        adaptive'e geçecekti. adaptive_barrier_ab_test_enabled açıksa
        (multi_timeframe_cascade_ab_test_enabled ile AYNI desen), statik
        anahtarın yerine HER karar bağımsız rastgele control (statik
        ATR)/treatment (adaptive) kovasına atanır ve decisions.
        experiment_bucket'a etiketlenir."""
        try:
            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.session_factory import SessionFactory

            with SessionFactory.get_session() as session:
                settings_repo = AppSettingsRepository(session)
                enabled = settings_repo.get("adaptive_barrier_enabled") == "true"
                ab_test_enabled = settings_repo.get("adaptive_barrier_ab_test_enabled") == "true"

            if ab_test_enabled:
                from services.ab_testing import assign_bucket

                bucket = assign_bucket()
                ctx.cognition.relevant_knowledge.append({
                    "type": "experiment_bucket",
                    "data": {"bucket": f"adaptive_barrier_v1:{bucket}"},
                })
                if bucket == "control":
                    return None
            elif not enabled:
                return None

            from analytics.adaptive_barrier_engine import recommend_barrier
            from analytics.barrier_table_repository import BarrierTableRepository

            stored = BarrierTableRepository().get_latest()
            if stored is None:
                return None

            from services.agent_memory import asset_class_trading_category

            features = ctx.market.features or {}
            context = {
                "direction": (ctx.decision.proposed_direction or "").upper(),
                "regime": features.get("long_term_trend_regime", "unknown"),
                "volatility_regime": features.get("volatility_regime", "unknown"),
                "asset_class": asset_class_trading_category(ctx.market.symbol) or "unknown",
                "confidence": ctx.decision.confidence or 0.0,
            }
            recommendation = recommend_barrier(context, stored["table"], group_by=tuple(stored["group_by"]))
            if recommendation is None:
                return None
            return recommendation["sl_pct"], recommendation["tp_pct"]
        except Exception as exc:
            logger.warning("adaptive_barrier_lookup_failed", error=str(exc))
            return None

    def _load_multipliers(self, direction: str | None = None) -> tuple[float, float, float]:
        """Faz 320 — direction=None (yön henüz bilinmiyor, ör. Tokens
        sayfasının önizleme uç noktası) SADECE stop_mult'u kullanan
        çağıranlar için var — stop_mult LONG/SHORT için AYNI (ikisi de
        2.5), bu yüzden yön bilinmese de doğru sonuç döner. target_mult
        bu durumda muhafazakâr/eski tek-oran davranışına (SHORT değeri)
        düşer — hiçbir çağıran yönü bilmeden hedef mesafesini KULLANMAZ,
        sadece stop_mult'u okuyan tokens.py bu varsayılanla etkilenmez."""
        is_long = (direction or "").upper() == "LONG"
        default_stop = self.DEFAULT_STOP_ATR_MULT_LONG if is_long else self.DEFAULT_STOP_ATR_MULT_SHORT
        default_target = self.DEFAULT_TARGET_ATR_MULT_LONG if is_long else self.DEFAULT_TARGET_ATR_MULT_SHORT
        stop_key = "stop_atr_mult_long" if is_long else "stop_atr_mult_short"
        target_key = "target_atr_mult_long" if is_long else "target_atr_mult_short"
        try:
            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.session_factory import SessionFactory

            with SessionFactory.get_session() as session:
                settings_repo = AppSettingsRepository(session)
                stop_mult = float(settings_repo.get(stop_key) or default_stop)
                target_mult = float(settings_repo.get(target_key) or default_target)
                min_stop_pct = float(settings_repo.get("min_stop_pct") or self.DEFAULT_MIN_STOP_PCT)
                return stop_mult, target_mult, min_stop_pct
        except Exception as exc:
            logger.warning("risk_multiplier_settings_load_failed", error=str(exc))
            return default_stop, default_target, self.DEFAULT_MIN_STOP_PCT


class DecisionFusionStage:
    def __init__(self):
        self.fusion = DecisionFusion()

    def execute(self, ctx: CognitiveCycleContext, belief: Belief, opinions: list | None = None) -> CognitiveCycleContext:
        return self.fusion.evaluate(ctx, belief, opinions)


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
        # Kullanıcı bulgusu: explain sayfası tek bir confidence sayısı
        # gösteriyordu, portföy korelasyon/ENB indiriminin (services/
        # orchestrator.py::_apply_portfolio_fusion) confidence'ı MetaStage'in
        # ACT/REDUCE kararından SONRA düşürdüğü hiç görünmüyordu — "%74
        # güvenli bir ajan varken nihai karar neden %28 çıktı" sorusunun
        # cevabı DB'de yoktu. decision_fusion_entries ile AYNI desen.
        portfolio_confidence_discounts = []
        experiment_bucket = None

        if hasattr(ctx, "cognition"):
            for item in ctx.cognition.relevant_knowledge:
                if item.get("type") == "decision_fusion":
                    decision_fusion_entries.append(item.get("data"))
                if item.get("type") == "portfolio_confidence_discount":
                    portfolio_confidence_discounts.append(item.get("data"))

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
            portfolio_confidence_discounts,
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

        # Faz 370-devam — kritik bulgu (canlı olay, 2026-08-29): engines/
        # risk_engine.py'nin ön kapısı (Faz 211'den beri) max_position_
        # size'ı ($ notional tavanı) proposed_size*current_price ile
        # karşılaştırıyordu — ama bu SON kapı final_size'ı (HAM birim
        # sayısı) doğrudan aynı limitle kıyaslıyordu. Pahalı varlıklarda
        # (BTC ~0.006 birim) bu asla tetiklenmiyordu, ama bugün watchlist'e
        # eklenen ucuz meme coin'lerde (ör. ARKMUSDT ~$0.11) AYNI dolar
        # tutarı binlerce birime denk geliyor — GERÇEK $630'luk bir
        # pozisyon "final size 5248.41 > limit 5000.0" diye yanlışlıkla
        # reddediliyordu (final_size ham birim, limit dolar niyetliydi).
        # Ön kapıyla AYNI notional dönüşümü burada da uygulanıyor —
        # current_price yoksa (bazı testler market verisi kurmuyor) eski
        # ham karşılaştırmaya düşülüyor, geriye dönük uyumlu.
        current_price = (ctx.market.raw_snapshot or {}).get("close")
        final_size_notional = final_size * current_price if current_price else final_size

        max_size = limits.get("max_position_size")
        if max_size and final_size_notional > max_size.value:
            reasons.append(RiskReason(
                code="POST_FUSION_SIZE_EXCEEDED",
                message="Final size " + str(final_size_notional) + " > limit " + str(max_size.value),
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

        # Faz 358 — kullanıcı bulgusu: yukarıdaki SAYI-bazlı gate kullanıcı
        # isteğiyle 1000'e gevşetilip fiilen devre dışı bırakıldı (test
        # modunda kısıtlama gereksiz) — ama "aynı sembol/yönde ne kadar $
        # bağlı" sorusuna hiçbir gate bakmıyordu (gerçek olay: XAUTUSDT
        # LONG'da 17 pozisyon, %0.15'lik bir bantta). Bu, AYRI ve
        # tamamlayıcı bir kontrol — ENB/Cross-Symbol Correlation Filter'a
        # (orchestrator.py::_apply_portfolio_fusion) BİLEREK eklenmedi: o
        # mekanizma FARKLI sembollerin çeşitlendirmesini ölçüyor, tek bir
        # sembolün kendi içindeki yığılmasını değil — denenip yanlış yönde
        # sonuç verdiği doğrulandı (bkz. commit geçmişi). max_capital_pct
        # ile AYNI, basit "toplam $ tavanı" ilkesi — SADECE bu sembol/yön
        # için.
        if (
            final_direction is not None
            and ctx.risk.max_same_symbol_direction_capital_pct is not None
            and ctx.risk.max_same_symbol_direction_capital_pct > 0
            and ctx.risk.starting_capital
        ):
            existing_notional = ctx.risk.same_direction_open_notional.get(final_direction, 0.0)
            cap = ctx.risk.starting_capital * ctx.risk.max_same_symbol_direction_capital_pct
            if existing_notional >= cap:
                reasons.append(RiskReason(
                    code="MAX_SAME_SYMBOL_DIRECTION_CAPITAL",
                    message=(
                        f"${existing_notional:,.0f} {final_direction} notional already open on this symbol "
                        f">= cap ${cap:,.0f} ({ctx.risk.max_same_symbol_direction_capital_pct:.1%} of capital)"
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
