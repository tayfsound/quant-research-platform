"""Context Adapter — ham piyasa verisini ajan bağlamlarına dönüştürür."""
from contracts.context import CognitiveCycleContext
from contracts.macro import MacroContext
from contracts.sentiment import SentimentContext
from contracts.onchain import OnChainContext
from contracts.technical import TechnicalContext

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
