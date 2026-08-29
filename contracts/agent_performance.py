"""Agent Performance — context-aware zenginleştirme."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentPerformanceRecord(BaseModel):

    id: UUID = Field(default_factory=uuid4)

    agent_domain: str
    timestamp: datetime = Field(default_factory=datetime.now)

    # Faz 268-sonrası — gerçek bulgu: timestamp burada KAYIT anını (pozisyon
    # KAPANDIĞINDA record() çağrılır) temsil ediyor, ajanın kararı VERDİĞİ
    # anı değil. Eski (ör. bir hafta önce açılmış) pozisyonların büyük bir
    # grubu AYNI GÜN kapanınca (backlog), get_summary()'nin "en yeni N kayıt"
    # penceresi o günün GERÇEK yeni kararlarını değil, o eski/bozuk dönemde
    # verilmiş kararları görüyordu — hem sahte-yüksek hem sahte-düşük
    # güvenilirlik üretiyordu (bkz. get_summary yorumu). decision_opened_at,
    # pozisyonun GERÇEKTEN açıldığı (kararın verildiği) an — None ise (bu
    # alan eklenmeden önceki eski kayıtlar) timestamp'e düşülüyor, geriye
    # dönük uyumlu.
    decision_opened_at: datetime | None = None

    direction: str
    confidence: float
    # Faz 369-devam — bkz. contracts/agent.py::AgentOpinion.raw_confidence.
    # Kalibrasyon ÖNCESİ ham değer — SADECE bu alan eklendikten sonraki
    # yeni kararlarda dolu, eski kayıtlarda None (geriye dönük kurtarılamaz).
    raw_confidence: float | None = None
    was_correct: bool

    # Faz 248: backtest motorunu öğrenme döngüsüne bağlarken eklendi —
    # gerçek parayla açılmış canlı işlemleri, gerçek geçmiş veri üzerinde
    # simüle edilmiş backtest "denemelerinden" AYIRT ETMEK için. Asla
    # sessizce karıştırma ilkesi: ikisi aynı dosyada birikir ama her
    # zaman filtrelenebilir/denetlenebilir kalır.
    source: str = "live"

    # Decision quality metrics
    decision_score: float = 0.0
    r_multiple: float = 0.0
    pnl: float = 0.0

    # Failure analysis
    failure_type: str = ""

    symbol: str = ""
    market_regime: str = ""
    timeframe: str = ""

    volatility: float = 0.0
    session: str = ""

    spread: float = 0.0
    funding: float = 0.0
    leverage: float = 0.0

    holding_time_minutes: int = 0

    news_type: str = ""
    reasoning: str = ""
    error_analysis: str = ""


class AgentPerformanceSummary(BaseModel):

    agent_domain: str

    overall_accuracy: float = 0.0
    total_predictions: int = 0

    by_symbol: dict[str, float] = Field(default_factory=dict)
    by_regime: dict[str, float] = Field(default_factory=dict)
    by_timeframe: dict[str, float] = Field(default_factory=dict)
    by_session: dict[str, float] = Field(default_factory=dict)
    by_volatility: dict[str, float] = Field(default_factory=dict)

    recent_accuracy: float = 0.0

    # Advanced performance metrics
    average_r_multiple: float = 0.0
    average_pnl: float = 0.0
    expected_value: float = 0.0
    risk_adjusted_score: float = 0.0

    common_errors: list[str] = Field(default_factory=list)
