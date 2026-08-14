"""Agent Sözleşmesi — intrinsic_trust, performance_weight, effective_influence."""
from abc import abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field


class AgentDomain(StrEnum):
    TECHNICAL = "technical"
    MACRO = "macro"
    ONCHAIN = "onchain"
    NEWS = "news"
    PSYCHOLOGY = "psychology"
    QUANT = "quant"
    RISK = "risk"
    BEHAVIORAL = "behavioral"
    ORDER_FLOW = "order_flow"
    PORTFOLIO = "portfolio"
    SOURCE_RELIABILITY = "source_reliability"
    EXECUTIVE = "executive"
    ALTER_EGO = "alter_ego"
    SENTIMENT = "sentiment"
    EPISTEMOLOGY = "epistemology"
    TIME = "time"
    PATTERN = "pattern"
    RELATIVE_STRENGTH = "relative_strength"

# Faz 229: kritik bulgu — 9 oy-veren ajanın gerçek listesi (bkz. "Agent
# kalitesi turu 2", CURRENT_STATE.md). AgentDomain enum'daki diğer roller
# (news/psychology/behavioral/risk/portfolio/source_reliability/executive/
# alter_ego) kritik/annotator, WeightOptimizer'ın ağırlıklandırdığı oy-veren
# ajanlar değil. Bu liste önceden sadece services/position_closer.py'de
# yerel bir sabitti (`_VALID_AGENT_DOMAINS`) — services/learning_loop.py ve
# services/weight_optimizer.py aynı doğrulamayı hiç yapmıyordu, `opinion.
# get("domain", "unknown")` gibi sessiz fallback'lerle AgentMemory'ye/
# WeightOptimizer'a sahte bir "unknown" ajan domain'i sızdırıyordu — gerçek
# ağırlık önerilerini ve insan onayına giden diff tablosunu kirletiyordu.
#
# Faz 242-243: 10. oy-veren ajan eklendi (Relative Strength — bkz.
# agents/relative_strength_agent.py).
VOTING_AGENT_DOMAINS = frozenset({
    AgentDomain.TECHNICAL, AgentDomain.MACRO, AgentDomain.ONCHAIN,
    AgentDomain.SENTIMENT, AgentDomain.PATTERN, AgentDomain.QUANT,
    AgentDomain.ORDER_FLOW, AgentDomain.TIME, AgentDomain.EPISTEMOLOGY,
    AgentDomain.RELATIVE_STRENGTH,
})

class AgentOpinion(BaseModel):
    """6 boyutlu uzman görüşü + epistemik katmanlar."""
    agent_id: str = ""
    domain: AgentDomain
    direction: str = ""

    confidence: float = 0.0
    uncertainty: float = 0.0
    data_quality: float = 0.8
    evidence_strength: float = 0.5
    freshness: float = 0.8
    source_reliability: float = 0.8
    evidence: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    # Faz 268-sonrası: Feature Importance — SHAP gibi bir YAKLAŞIK
    # açıklama yöntemi değil (bu ajanların skorlama mantığı zaten kesin,
    # katkısal/additive bir fonksiyon — kara kutu bir model değil ki
    # yaklaşıklamak gereksin). Her ajan, kendi score'unu OLUŞTURAN her
    # isimli sinyalin GERÇEK sayısal katkısını burada topluyor — hangi
    # feature'ın kararı ne kadar etkilediği tahmin değil, kesin. Boş dict
    # = bu ajan henüz enstrümante edilmedi (fail-closed, uydurulmuş bir
    # katkı asla raporlanmaz).
    feature_contributions: dict[str, float] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)

    # Epistemik katmanlar: intrinsic_trust, performance_weight, effective_influence
    intrinsic_trust: float = 0.0
    performance_weight: float = 1.0
    effective_influence: float = 0.0

    # Faz 268-sonrası — "olasılıksal mimari" vizyonunun EN UCUZ, bağlayıcı
    # olmayan hazırlık adımı (kullanıcı onayıyla, kasıtlı olarak SADECE bu
    # kadarı: opsiyonel/geriye-uyumlu alanlar, HİÇBİR ajan/karar mantığı
    # henüz bunları OKUMUYOR — "yeni karmaşıklık kendi edge'ini
    # kanıtlamalı" ilkesi gereği). Amaç: bir ajan tek bir skaler confidence
    # yerine, isterse fiyatın öngörülen dağılımını (predictive_mu/sigma —
    # log-getiri uzayında ortalama/belirsizlik) raporlayabilsin. None =
    # bu ajan henüz bunu üretmiyor (fail-closed, uydurulmuş bir dağılım
    # asla varsayılmaz). calibration_factor de aynı şekilde opsiyonel —
    # services/confidence_calibration.py'nin ZATEN yaptığı ampirik
    # kalibrasyonun yerini almıyor, gelecekte bir ajanın KENDİ
    # hesapladığı bir kalibrasyon sinyali için ayrılmış bir alan.
    predictive_mu: float | None = None
    predictive_sigma: float | None = None
    calibration_factor: float | None = None

    def recalculate(self) -> "AgentOpinion":
        """Kontrollü yeniden hesaplama — tam determinizm."""
        self.intrinsic_trust = (
            self.confidence * 0.25 +
            self.data_quality * 0.20 +
            self.evidence_strength * 0.20 +
            self.freshness * 0.15 +
            self.source_reliability * 0.20
        )
        self.effective_influence = self.intrinsic_trust * self.performance_weight
        return self

class AgentChallenge(BaseModel):
    challenger_domain: AgentDomain
    target_domain: AgentDomain
    reason: str
    confidence: float
    evidence_strength: float = 0.5
    urgency: str = "normal"
    source_reliability: float = 0.8
    suggested_adjustment: str = ""

class AgentResponse(BaseModel):
    responder_domain: AgentDomain
    original_challenge: AgentChallenge
    response: str
    evidence_quality_change: float = 0.0
    confidence_change: float = 0.0

class DebateRound(BaseModel):
    round_number: int
    challenges: list[AgentChallenge] = Field(default_factory=list)
    responses: list[AgentResponse] = Field(default_factory=list)

class CognitiveAudit(BaseModel):
    confirmation_bias: float = 0.0
    herd_behavior_risk: float = 0.0
    overconfidence_risk: float = 0.0
    information_independence: float = 1.0
    missing_information: list[str] = Field(default_factory=list)
    recommended_action: str = ""
    epistemology_score: float = 0.5

class DebateResult(BaseModel):
    original_opinions: list[AgentOpinion]
    rounds: list[DebateRound] = Field(default_factory=list)
    cognitive_audit: CognitiveAudit | None = None
    final_direction: str
    final_confidence: float
    reasoning: str
    # Faz 268-sonrası — kritik bulgu (üçüncü taraf mimari incelemesi +
    # gerçek kod doğrulaması): production'da hiçbir ResponderAgent kayıtlı
    # değil, yani RiskChallenger'ın ürettiği itirazlar hiçbir zaman
    # cevaplanmıyor ama önceden de hiçbir etkileri olmuyordu — sadece
    # explainability zincirine (debate_result) yazılıyorlardı, gerçek oy
    # ağırlığına (BeliefEngine.apply_weights) hiç dokunmuyorlardı. Bu alan,
    # domain başına "cevapsız itiraz çarpanı" (0, 1] taşıyor —
    # CouncilOrchestrator.deliberate() bunu gerçek opinion.performance_
    # weight'e uyguluyor (benching ile AYNI mekanizma).
    unanswered_challenge_penalties: dict[str, float] = Field(default_factory=dict)

class BaseAgent(Protocol):
    @abstractmethod
    def analyze(self, context: dict) -> AgentOpinion: ...

class ChallengerAgent(Protocol):
    @abstractmethod
    def challenge(self, opinion: AgentOpinion, context: dict) -> list[AgentChallenge]: ...

class ResponderAgent(Protocol):
    @abstractmethod
    def respond(self, challenge: AgentChallenge, context: dict) -> AgentResponse: ...
