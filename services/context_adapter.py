"""Context Adapter — ham piyasa verisini ajan bağlamlarına dönüştürür."""
from datetime import UTC, datetime

from contracts.context import CognitiveCycleContext
from contracts.epistemology import EpistemologyContext
from contracts.macro import MacroContext
from contracts.onchain import OnChainContext
from contracts.order_flow import OrderFlowContext
from contracts.pattern import PatternContext
from contracts.quant import QuantContext
from contracts.sentiment import SentimentContext
from contracts.technical import TechnicalContext
from contracts.time_context import TimeContext

_EXPECTED_FEATURES = ("RSI", "ema", "macd", "trend", "volatility_regime")


class ContextAdapter:
    def _get(self, ctx: CognitiveCycleContext, key: str, default=None):
        """Hem features hem raw_snapshot'tan değer okur."""
        if key in ctx.market.raw_snapshot:
            return ctx.market.raw_snapshot[key]
        return ctx.market.features.get(key, default)

    def to_macro(self, ctx: CognitiveCycleContext) -> MacroContext:
        return MacroContext(
            inflation_trend=self._get(ctx, "inflation_trend", "stable"),
            liquidity_condition=self._get(ctx, "liquidity_condition", "neutral"),
            central_bank_bias=self._get(ctx, "central_bank_bias", "neutral"),
            employment_trend=self._get(ctx, "employment_trend", "stable"),
        )

    def to_sentiment(self, ctx: CognitiveCycleContext) -> SentimentContext:
        return SentimentContext(
            fear_greed_index=self._get(ctx, "fear_greed_index", 50.0),
            social_media_sentiment=self._get(ctx, "social_media_sentiment", 0.0),
            news_tone=self._get(ctx, "news_tone", "neutral"),
            positioning=self._get(ctx, "positioning", "neutral"),
        )

    def to_onchain(self, ctx: CognitiveCycleContext) -> OnChainContext:
        return OnChainContext(
            exchange_outflow_24h=self._get(ctx, "exchange_outflow_24h", 0.0),
            exchange_inflow_24h=self._get(ctx, "exchange_inflow_24h", 0.0),
            whale_accumulation=self._get(ctx, "whale_accumulation", False),
            whale_distribution=self._get(ctx, "whale_distribution", False),
            stablecoin_mint_24h=self._get(ctx, "stablecoin_mint_24h", 0.0),
            mvrv_zscore=self._get(ctx, "mvrv_zscore", 0.0),
        )

    def to_technical(self, ctx: CognitiveCycleContext) -> TechnicalContext:
        return TechnicalContext(
            trend=self._get(ctx, "trend", "neutral"),
            momentum=self._get(ctx, "momentum", "neutral"),
            market_structure=self._get(ctx, "market_structure", "neutral"),
            volume_confirmation=self._get(ctx, "volume_confirmation", False),
            rsi_value=self._get(ctx, "RSI", 50.0),
            ema_alignment=self._get(ctx, "ema_alignment", "neutral"),
            volatility_regime=self._get(ctx, "volatility_regime", "normal"),
        )

    def to_pattern(self, ctx: CognitiveCycleContext) -> PatternContext:
        return PatternContext(
            structure_phase=self._get(ctx, "structure_phase", "neutral"),
            break_of_structure=self._get(ctx, "break_of_structure", "none"),
            change_of_character=self._get(ctx, "change_of_character", False),
            fair_value_gap=self._get(ctx, "fair_value_gap", "none"),
            swing_structure=self._get(ctx, "swing_structure", "mixed"),
            liquidity_sweep=self._get(ctx, "liquidity_sweep", "none"),
        )

    def to_quant(self, ctx: CognitiveCycleContext) -> QuantContext:
        return QuantContext(
            zscore=self._get(ctx, "zscore", 0.0),
            realized_vol_percentile=self._get(ctx, "realized_vol_percentile", 50.0),
            autocorrelation=self._get(ctx, "autocorrelation", 0.0),
            hurst_exponent=self._get(ctx, "hurst_exponent", 0.5),
        )

    def to_order_flow(self, ctx: CognitiveCycleContext) -> OrderFlowContext:
        """Diğer to_*() metotlarının aksine gerçek bir DB okuması içeriyor —
        Faz 186'da eklenen order_book_snapshots'tan en son satırı okur.
        WeightRepository.get_latest()'in CouncilOrchestrator.deliberate()
        içinde zaten yaptığı senkron DB erişimiyle aynı desen."""
        from contracts.market_data import DataSource
        from database.repositories.market_data_repository import MarketDataRepository
        from database.session_factory import SessionFactory

        symbol = ctx.market.symbol or ""
        imbalance, spread_bps = 0.0, 0.0
        if symbol:
            with SessionFactory.get_session() as session:
                snapshot = MarketDataRepository(session).get_latest_order_book_snapshot(DataSource.BINANCE, symbol)
                if snapshot:
                    imbalance = snapshot["imbalance"]
                    spread_bps = snapshot["spread_bps"]

        return OrderFlowContext(
            bid_ask_imbalance=self._get(ctx, "bid_ask_imbalance", imbalance),
            spread_bps=self._get(ctx, "spread_bps", spread_bps),
            aggressive_buy_ratio=self._get(ctx, "aggressive_buy_ratio", 0.5),
        )

    def to_time(self, ctx: CognitiveCycleContext) -> TimeContext:
        now = datetime.now(UTC)
        hour = now.hour
        if 0 <= hour < 7 or hour >= 21:
            session = "asia"
        elif 7 <= hour < 12:
            session = "europe"
        elif 12 <= hour < 16:
            session = "overlap"
        else:
            session = "us"

        next_funding_hour = min(h for h in (0, 8, 16, 24) if h > hour)
        hours_to_funding = (next_funding_hour - hour) - now.minute / 60

        return TimeContext(
            session=self._get(ctx, "session", session),
            day_of_week=self._get(ctx, "day_of_week", now.strftime("%A")),
            hours_to_funding=self._get(ctx, "hours_to_funding", round(hours_to_funding, 2)),
            is_weekend=self._get(ctx, "is_weekend", now.weekday() >= 5),
        )

    def to_epistemology(self, ctx: CognitiveCycleContext) -> EpistemologyContext:
        present = sum(1 for key in _EXPECTED_FEATURES if self._get(ctx, key, None) is not None)
        completeness = present / len(_EXPECTED_FEATURES)
        age_seconds = max(0.0, (datetime.now() - ctx.timestamp.replace(tzinfo=None)).total_seconds())

        return EpistemologyContext(
            feature_completeness=round(completeness, 3),
            data_age_seconds=age_seconds,
            known_unknown_count=len(_EXPECTED_FEATURES) - present,
        )
