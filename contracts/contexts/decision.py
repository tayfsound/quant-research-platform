"""Decision — ActionType, confidence, uncertainty, reason, reconsideration."""
from enum import StrEnum

from pydantic import BaseModel


class ActionType(StrEnum):
    ENTER_LONG = "ENTER_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    WAIT = "WAIT"
    EXIT = "EXIT"
    REDUCE = "REDUCE"
    RECONSIDER = "RECONSIDER"

class DecisionReason(StrEnum):
    NO_SIGNAL = "NO_SIGNAL"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    HIGH_RISK = "HIGH_RISK"
    STRONG_SIGNAL = "STRONG_SIGNAL"
    MEMORY_SUPPORTED = "MEMORY_SUPPORTED"

class Decision(BaseModel):
    proposed_direction: str = ""
    proposed_size: float = 0.0
    risk_adjusted_size: float = 0.0
    final_direction: str = ""
    final_size: float = 0.0
    action: ActionType = ActionType.WAIT
    reason: DecisionReason = DecisionReason.NO_SIGNAL
    confidence: float = 0.0
    uncertainty: float = 1.0
    reconsideration_count: int = 0
    # Faz 329 — Kimi'nin (üçüncü taraf inceleme) bulduğu adlandırma tuzağı:
    # eskiden take_profit/stop_loss isimlendirilen bu iki alan MUTLAK FİYAT
    # DEĞİL, entry_price'a göre bir MESAFE/MAGNİTÜD (her zaman >=0, yöne
    # göre +/- işareti services/decision_recorder.py'de uygulanıyor) —
    # "stop_loss" ismi bunu okuyan yeni bir geliştiriciyi "bu bir fiyat
    # seviyesi" diye yanıltabilirdi (canlı bir bug'a yol açmadı, tüm mevcut
    # kullanımlar zaten doğru yorumluyordu, ama isim netleştirildi).
    take_profit_distance: float | None = None
    stop_loss_distance: float | None = None
    filled_price: float | None = None
