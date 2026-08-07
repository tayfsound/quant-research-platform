"""Kaldıraç ve teminat yönetimi."""
from dataclasses import dataclass, field

# Faz 255: kullanıcı isteği — gerçek kaldıraç desteği. Binance'in gerçek
# maintenance margin oranı bildirim dilimine (notional büyüklüğüne) göre
# kademeli değişir (küçük pozisyonlarda genelde %0.4-%0.5 civarı) — burada
# tek, sabit, konservatif bir yaklaşık değer kullanılıyor (dilim tablosunu
# tam olarak yansıtmak ayrı bir API çağrısı + karmaşıklık gerektirir).
# Bu İCAT EDİLMİŞ bir sayı değil, endüstri standardı yaklaşık izole
# margin likidasyon formülü — gerçek borsalarda kullanılan (fiyat X
# olduğunda pozisyon eşiği ~0 equity'ye ulaşır) formülün ta kendisi.
DEFAULT_MAINTENANCE_MARGIN_RATE = 0.005


def compute_liquidation_price(
    entry_price: float, direction: str, leverage: float,
    maintenance_margin_rate: float = DEFAULT_MAINTENANCE_MARGIN_RATE,
) -> float | None:
    """İzole margin, yaklaşık likidasyon fiyatı. leverage<=1 ise (spot,
    kaldıraçsız) None döner — likidasyon kavramı spot pozisyonda yok."""
    if leverage is None or leverage <= 1.0 or entry_price is None or entry_price <= 0:
        return None
    d = (direction or "").upper()
    if d == "LONG":
        return entry_price * (1 - 1 / leverage + maintenance_margin_rate)
    if d == "SHORT":
        return entry_price * (1 + 1 / leverage - maintenance_margin_rate)
    return None


@dataclass
class MarginAccount:
    balance: float = 100_000.0
    positions: dict[str, "Position"] = field(default_factory=dict)

    def open_position(self, symbol: str, side: str, quantity: float, price: float, leverage: float):
        notional = quantity * price
        margin = notional / leverage
        if margin > self.balance:
            raise ValueError("Yetersiz teminat")
        self.balance -= margin
        self.positions[symbol] = Position(
            symbol=symbol, side=side, quantity=quantity,
            entry_price=price, leverage=leverage, margin_used=margin
        )

    def close_position(self, symbol: str, exit_price: float):
        if symbol not in self.positions:
            return 0.0
        pos = self.positions.pop(symbol)
        pnl = (exit_price - pos.entry_price) * pos.quantity if pos.side == "long" \
              else (pos.entry_price - exit_price) * pos.quantity
        self.balance += pos.margin_used + pnl
        return pnl

@dataclass
class Position:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    leverage: float
    margin_used: float
