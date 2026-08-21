"""Credit Domain Contract — Faz 333. Tahvil piyasası kredi koşulları,
hisse/kripto gibi risk varlıklarından tarihsel olarak ÖNCE sinyal verir
("credit leads equity")."""
from datetime import datetime

from pydantic import BaseModel, Field


class CreditContext(BaseModel):
    """CreditAgent için işlenmiş kredi/tahvil piyasası bağlamı."""
    yield_curve_signal: str = ""    # "inverted", "normal"
    credit_spread_trend: str = ""   # "widening", "narrowing", "stable"
    timestamp: datetime = Field(default_factory=datetime.now)
