"""Faz 200: pairs trading — gerçekten iki bacaklı bir işlem açıyor (spread'in
altta kalan tarafı LONG, üstte kalan tarafı SHORT), Council/agent oy sistemi
değil çünkü bu sinyal ajanların teknik görüşünden değil doğrudan iki fiyat
serisinin istatistiksel ilişkisinden geliyor. Yine de AYNI risk altyapısını
(RiskEngine — cooldown/ai_enabled/trading_mode/concurrent/capital) kullanıyor,
onu atlamıyor/gevşetmiyor."""
from datetime import UTC, datetime

from analytics.pairs_trading import (
    PAIR_CANDIDATES,
    ZSCORE_ENTRY_THRESHOLD,
    check_cointegration,
    compute_spread_zscore,
)
from contracts.context import CognitiveCycleContext
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.risk_limit_repository import load_active_limits
from database.session_factory import SessionFactory
from engines.risk_engine import RiskEngine
from market_data.features.signal_engine import compute_technical_signals
from market_data.ingestion.data_provider import RoutingProvider
from market_data.market_hours import is_market_open
from services.decision_recorder import DecisionRecorder
from services.risk_state import load_position_risk_state

STOP_ATR_MULT = 1.0
TARGET_ATR_MULT = 2.0  # RiskTargetStage'le aynı 1:2 konvansiyonu
LEG_SIZE = 0.2  # her bacak, RiskTargetStage'inkinden bağımsız, sabit-küçük bir boyut


class PairsTrader:
    def __init__(self, data_provider=None):
        self.data_provider = data_provider or RoutingProvider()
        self.recorder = DecisionRecorder()

    def check_and_trade_pairs(self) -> list[dict]:
        with SessionFactory.get_session() as session:
            ai_enabled = AppSettingsRepository(session).get("ai_enabled") == "true"

        if not ai_enabled:
            return [{"skipped": "ai_disabled"}]

        results = []
        for sym_a, sym_b in PAIR_CANDIDATES:
            result = self._check_pair(sym_a, sym_b)
            if result is not None:
                results.append(result)
        return results

    def _check_pair(self, sym_a: str, sym_b: str) -> dict | None:
        if not (is_market_open(sym_a) and is_market_open(sym_b)):
            return {"pair": f"{sym_a}/{sym_b}", "skipped": "market_closed"}

        data_a = self.data_provider.get_ohlcv(sym_a, "1m", limit=100)
        data_b = self.data_provider.get_ohlcv(sym_b, "1m", limit=100)
        if not data_a or not data_b or len(data_a) != len(data_b):
            return {"pair": f"{sym_a}/{sym_b}", "skipped": "no_data"}

        closes_a = [b.close for b in data_a]
        closes_b = [b.close for b in data_b]

        is_cointegrated, p_value = check_cointegration(closes_a, closes_b)
        if not is_cointegrated:
            return {"pair": f"{sym_a}/{sym_b}", "cointegrated": False, "p_value": p_value}

        z = compute_spread_zscore(closes_a, closes_b)
        if z is None or abs(z) < ZSCORE_ENTRY_THRESHOLD:
            return {"pair": f"{sym_a}/{sym_b}", "cointegrated": True, "p_value": p_value, "zscore": z}

        # z > 0: A, B'ye göre spread'in üstünde -> A pahalı (SHORT), B ucuz (LONG).
        if z > 0:
            long_sym, long_data = sym_b, data_b
            short_sym, short_data = sym_a, data_a
        else:
            long_sym, long_data = sym_a, data_a
            short_sym, short_data = sym_b, data_b

        opened = []
        for sym, data, direction in ((long_sym, long_data, "LONG"), (short_sym, short_data, "SHORT")):
            if self._open_leg(sym, data, direction, pair_label=f"{sym_a}/{sym_b}", zscore=z):
                opened.append(sym)

        return {
            "pair": f"{sym_a}/{sym_b}", "cointegrated": True, "p_value": p_value,
            "zscore": z, "opened_legs": opened,
        }

    def _open_leg(self, symbol: str, data, direction: str, pair_label: str, zscore: float) -> bool:
        ctx = CognitiveCycleContext()
        ctx.market.symbol = symbol
        ctx.market.raw_snapshot = {
            "close": data[-1].close,
            "pairs_trade": pair_label,
            "pairs_zscore": zscore,
        }
        ctx.decision.proposed_direction = direction
        ctx.decision.final_size = LEG_SIZE
        ctx.decision.filled_price = data[-1].close

        ctx.risk.limits = load_active_limits()
        risk_state = load_position_risk_state(symbol=symbol)
        ctx.risk.trading_mode = risk_state["trading_mode"]
        ctx.risk.open_position_count = risk_state["open_position_count"]
        ctx.risk.max_concurrent_positions = risk_state["max_concurrent_positions"]
        ctx.risk.capital_used_pct = risk_state["capital_used_pct"]
        ctx.risk.max_capital_pct = risk_state["max_capital_pct"]
        ctx.risk.seconds_since_last_trade = risk_state["seconds_since_last_trade"]
        ctx.risk.min_seconds_between_trades = risk_state["min_seconds_between_trades"]
        ctx.risk.ai_enabled = risk_state["ai_enabled"]
        ctx.risk.consecutive_losses = risk_state["consecutive_losses"]
        ctx.risk.kill_switch_consecutive_losses = risk_state["kill_switch_consecutive_losses"]

        # Not: bu, bacağın kendi ATR'sine göre standart bir stop/hedef —
        # spread'in ortalamaya dönüşünü (asıl pairs trading çıkış sinyali)
        # takip eden ayrı bir mekanizma değil. Bilinçli bir sınırlama:
        # spread-farkındalıklı kapanış, PositionCloser'ın çift bacakları
        # birbirine bağlaması gerektirir — ayrı, daha büyük bir iş.
        atr = compute_technical_signals(data).get("atr", 0.0) or 0.0
        if atr > 0:
            ctx.decision.stop_loss = atr * STOP_ATR_MULT
            ctx.decision.take_profit = atr * TARGET_ATR_MULT

        ctx = RiskEngine().execute(ctx)
        if ctx.risk.evaluation.verdict != "approved":
            return False

        self.recorder.record(ctx)
        return True
