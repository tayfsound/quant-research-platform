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


# Faz 260: kullanıcı bulgusu — "artık sabit ATR çalışmaz, kaldıraç var,
# daha da hızlı stop olurlar." Doğrulandı ama mekanizma farklı: stop_loss
# mesafesi kaldıraçtan bağımsız (hep günlük ATR'den), ama YÜKSEK kaldıraç
# + GENİŞ ATR kombinasyonunda likidasyon fiyatı stop'tan ÖNCE
# tetiklenebiliyor — pozisyon planlanan ~%5 kaybı hiç görmeden tüm
# teminatı kaybediyor. SAFETY_MULT=1.5: likidasyon mesafesi, stop
# mesafesinin en az 1.5 katı olsun isteniyor — ATR günden güne
# oynayabildiği için sıfır pay bırakmıyor.
SAFETY_MULT = 1.5


def max_safe_leverage(
    stop_distance_pct: float,
    safety_multiplier: float = SAFETY_MULT,
    maintenance_margin_rate: float = DEFAULT_MAINTENANCE_MARGIN_RATE,
    exchange_max_leverage: float = 125.0,
) -> float | None:
    """stop_distance_pct (ör. 0.0536 = %5.36) verilen bir stop mesafesi
    için, likidasyonun bu mesafenin en az safety_multiplier katı kadar
    uzakta kalmasını sağlayan en yüksek kaldıraç. stop_distance_pct
    None/<=0 ise (ATR hesaplanamadı, fail-closed) None döner."""
    if stop_distance_pct is None or stop_distance_pct <= 0:
        return None
    required_liq_distance = stop_distance_pct * safety_multiplier + maintenance_margin_rate
    if required_liq_distance <= 0:
        return None
    return min(exchange_max_leverage, 1.0 / required_liq_distance)


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
