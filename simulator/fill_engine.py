"""Simüle fill motoru."""
from dataclasses import dataclass
from typing import Optional
from simulator.fee_engine import FeeEngine
from simulator.slippage_model import SlippageModel

@dataclass
class FillResult:
    filled_price: float
    fee: float
    pnl: Optional[float]

# Faz 268e — kritik bulgu: services/orchestrator.py'nin GERÇEK, canlı
# çağırdığı tek yer (propose()/propose_medium_term()) buraya her zaman
# "LONG"/"SHORT" gönderiyor (bu sistemdeki TÜM yön alanlarının ortak
# sözleşmesi — DecisionEvent, AgentOpinion, her yerde). Ama SlippageModel.
# apply() sadece "BUY"/"SELL" biliyor (bkz. simulator/slippage_model.py,
# tests/test_simulator.py). "LONG" == "BUY" hiçbir zaman doğru olmadığı
# için apply() HER ZAMAN else dalına (price - slip) düşüyordu — SHORT için
# bu tesadüfen doğruydu (satışta olumsuz kayma = daha düşük fiyat) ama
# LONG için TERSTİ: gerçek bir alışta olumsuz kayma daha YÜKSEK fiyat
# demek olmalıyken, LONG pozisyonlar sistematik olarak daha DÜŞÜK (yapay
# olarak iyi) bir giriş fiyatıyla açılıyordu — hiçbir testte yakalanmadı
# çünkü test_simulator.py sadece "BUY"/"SELL" ile SlippageModel'i
# doğrudan test ediyordu, FillEngine üzerinden LONG/SHORT ile hiç değil.
_DIRECTION_TO_SIDE = {"LONG": "BUY", "SHORT": "SELL"}


class FillEngine:
    def __init__(self):
        self.fee = FeeEngine()
        self.slippage = SlippageModel()

    def simulate(self, decision: dict, market_price: float) -> FillResult:
        direction = decision.get("direction", "NEUTRAL")
        if direction == "NEUTRAL":
            return FillResult(filled_price=market_price, fee=0.0, pnl=0.0)

        side = _DIRECTION_TO_SIDE.get(direction, direction)
        size = decision.get("size", 1.0)
        filled = self.slippage.apply(market_price, side, size)
        notional = filled * size
        fee = self.fee.calculate(notional)
        return FillResult(filled_price=filled, fee=fee, pnl=None)
