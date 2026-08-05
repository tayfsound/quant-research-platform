"""Council Orchestrator — belief, opinions ve debate birlikte yönetilir."""
from agents.critics.alter_ego import AlterEgoChallenger
from agents.critics.risk_challenger import RiskChallenger
from contracts.agent import AgentDomain, AgentOpinion, DebateResult
from services.agent_debate import AgentDebate
from services.belief_engine import Belief, BeliefEngine
from services.council_reliability import ReliabilityAnnotator
from services.weight_repository import WeightRepository


class CouncilOrchestrator:
    def __init__(
        self,
        registry,
        belief_engine: BeliefEngine | None = None,
        pinned_weight_snapshot_id=None,
    ):
        self.registry = registry
        self.belief_engine = belief_engine or BeliefEngine()
        self.weight_repository = WeightRepository()
        self.active_weight_snapshot_id = None
        # If set, deliberate() uses this exact snapshot instead of
        # get_latest() — required for backtest determinism, otherwise a
        # decision simulated for a past bar would use weights learned from
        # data that (in a real run) wouldn't exist yet.
        self.pinned_weight_snapshot_id = pinned_weight_snapshot_id

        self.last_debate_result: DebateResult | None = None

        self.debate = AgentDebate(max_rounds=2)
        self.debate.register_challenger(
            AgentDomain.RISK,
            RiskChallenger()
        )
        # Agent kalitesi bulgusu: agent_debate.py::_run_cognitive_audit()
        # zaten AgentDomain.ALTER_EGO'yu challengers'tan arıyordu ama hiçbir
        # yerde register edilmediği için hep None dönüyordu, CognitiveAudit
        # (confirmation_bias/herd_behavior_risk/overconfidence_risk) hep boş
        # kalıyordu. Bu, "psychology"/"behavioral" domain'lerinin gerçek
        # karşılığı — ayrı, Sentiment'la çakışan oy-ajanları değil.
        self.debate.register_challenger(
            AgentDomain.ALTER_EGO,
            AlterEgoChallenger()
        )
        # Agent kalitesi bulgusu: SourceReliabilityAgent/ReliabilityAnnotator
        # tamamen yazılmış ve kendi testinde çalışıyordu ama hiçbir yerden
        # çağrılmıyordu — her ajanın source_reliability'si (intrinsic_trust'ın
        # %20'si, BeliefEngine.apply_weights()'in kullandığı effective_influence'ı
        # doğrudan etkiliyor) sonsuza kadar kendi hardcoded sabitinde kalıyordu,
        # gerçek geçmiş performansa göre hiç güncellenmiyordu.
        self.reliability_annotator = ReliabilityAnnotator()

    def deliberate(
        self,
        contexts: dict[AgentDomain, object]
    ) -> tuple[Belief, list[AgentOpinion]]:

        opinions: list[AgentOpinion] = []

        for domain, ctx in contexts.items():
            if ctx is None:
                continue

            agent = self.registry.get(domain)
            if not agent:
                continue

            try:
                opinion = agent.analyze(ctx)
                opinions.append(opinion)

            except Exception as e:
                print(f"[Council] {domain} agent failed: {e}")

        if not opinions:
            self.last_debate_result = None
            return Belief(direction="WAIT", total_opinions=0), []

        # Her ajanın source_reliability'sini kendi hardcoded sabitinden,
        # gerçek geçmiş performansına (son 10 kararının ortalama
        # confidence'i) göre güncelle — recalculate() intrinsic_trust/
        # effective_influence'ı bu yeni değerle yeniden hesaplar.
        annotated = self.reliability_annotator.annotate(
            [{"domain": o.domain.value, "confidence": o.confidence} for o in opinions]
        )
        for opinion, info in zip(opinions, annotated):
            opinion.source_reliability = info["source_reliability"]
            if info.get("benched"):
                # Auto-bench: bu domain art arda BENCH_AFTER kez düşük
                # güvenilirlik gösterdi. Metafor değil — performance_weight=0
                # effective_influence'ı (intrinsic_trust * performance_weight)
                # gerçekten sıfırlar, yani bu oy nihai karara hiç katkı
                # vermiyor. Opinion listede KALIYOR (sessizce yutulmuyor,
                # explainability zincirinde görünür) ve gelecek cycle'larda
                # gerçekten toparlanırsa (RECOVERY_THRESHOLD) otomatik geri
                # döner.
                opinion.performance_weight = 0.0
                opinion.caveats.append(
                    f"Benched: {opinion.domain.value} reliability stayed below "
                    f"{self.reliability_annotator.agent.BENCH_THRESHOLD} for "
                    f"{self.reliability_annotator.agent.BENCH_AFTER}+ cycles — vote weight zeroed until it recovers."
                )
            opinion.recalculate()

        self.last_debate_result = self.debate.run_debate(
            opinions,
            self._build_debate_context(contexts, opinions),
        )

        if self.pinned_weight_snapshot_id is not None:
            snapshot = self.weight_repository.get_by_id(self.pinned_weight_snapshot_id)
        else:
            snapshot = self.weight_repository.get_latest()
        self.active_weight_snapshot_id = snapshot.id if snapshot else None

        if snapshot:
            belief = self.belief_engine.apply_weights(
                opinions,
                snapshot
            )
        else:
            belief = self.belief_engine.synthesize(opinions)

        return belief, opinions

    _VOLATILITY_REGIME_TO_SCORE = {"low": 0.2, "normal": 0.4, "high": 0.8}

    def _build_debate_context(
        self,
        contexts: dict[AgentDomain, object],
        opinions: list[AgentOpinion],
    ) -> dict:
        """Agent kalitesi bulgusu: RiskChallenger.challenge() üretimde her
        zaman `context={}` alıyordu (deliberate() bunu hardcoded {} ile
        çağırıyordu), yani challenger'ın en önemli iki kontrolü —
        "yüksek volatilitede aşırı güven" ve "yön kalabalığı riski" —
        `context.get(...)` her zaman 0.0'a düştüğü için hiçbir zaman
        gerçekten tetiklenemiyordu (eşikler 0.7/0.6, sabit 0.0 asla
        geçemez). Üçüncü kontrol (data_quality < 0.5) da hiç
        tetiklenmiyordu çünkü 4 gerçek ajanın hepsi data_quality'yi
        sabit ≥0.75 olarak raporluyor. Sonuç: risk challenge katmanı
        production'da fiilen hiçbir şey yapmıyordu. Bu, gerçek,
        elimizdeki verilerden hesaplanan bir context inşa ediyor.
        """
        volatility = 0.0
        technical_ctx = contexts.get(AgentDomain.TECHNICAL)
        if technical_ctx is not None:
            regime = getattr(technical_ctx, "volatility_regime", "normal")
            volatility = self._VOLATILITY_REGIME_TO_SCORE.get(regime, 0.4)

        crowding_risk = 0.0
        directional = [o for o in opinions if o.direction != "WAIT"]
        if directional:
            counts: dict[str, int] = {}
            for o in directional:
                counts[o.direction] = counts.get(o.direction, 0) + 1
            crowding_risk = max(counts.values()) / len(directional)

        return {"volatility": volatility, "crowding_risk": crowding_risk}
