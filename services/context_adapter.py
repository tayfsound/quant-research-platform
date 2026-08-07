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
        # Faz 197: gerçek FRED verisi — ağ hatası/key yoksa provider zaten
        # None döner, o zaman dürüstçe nötr varsayılana düşülüyor (icat
        # edilmiş bir "trend" değil).
        from market_data.macro.fred_provider import (
            fetch_central_bank_bias,
            fetch_employment_trend,
            fetch_inflation_trend,
            fetch_liquidity_condition,
        )

        return MacroContext(
            inflation_trend=self._get(ctx, "inflation_trend", fetch_inflation_trend() or "stable"),
            liquidity_condition=self._get(ctx, "liquidity_condition", fetch_liquidity_condition() or "neutral"),
            central_bank_bias=self._get(ctx, "central_bank_bias", fetch_central_bank_bias() or "neutral"),
            employment_trend=self._get(ctx, "employment_trend", fetch_employment_trend() or "stable"),
        )

    def to_sentiment(self, ctx: CognitiveCycleContext) -> SentimentContext:
        # Faz 198: Crypto Fear & Greed Index sadece kripto için anlamlı —
        # AAPL/altın için "kripto piyasası korkuyor mu" alakasız olurdu.
        symbol = ctx.market.symbol or ""
        real_fgi = None
        real_positioning = None
        if symbol.upper().endswith(("USDT", "BUSD", "USDC", "FDUSD")):
            from market_data.sentiment.fear_greed_provider import fetch_fear_greed_index
            real_fgi = fetch_fear_greed_index()

            # Faz 215: gerçek bulgu — "positioning" hep sabit "neutral"
            # kullanıyordu, önceki bir not bunun "genelde ücretli/karmaşık"
            # olduğunu varsaymıştı ama Binance Futures'ın global long/short
            # hesap oranı gerçekten ücretsiz/kimliksiz erişilebiliyor.
            # Sadece gerçek bir futures kontratı olan semboller için (ör.
            # PAXGUSDT/XAUTUSDT'de futures yok) — yoksa None, dürüstçe
            # "neutral"e düşer, uydurulmaz.
            from market_data.sentiment.positioning_provider import fetch_positioning
            real_positioning = fetch_positioning(symbol)

        # Faz 215: gerçek bulgu — "news_tone" hep sabit "neutral" kullanıyordu.
        # CoinDesk'in gerçek, ücretsiz RSS akışından gerçek başlıklar +
        # şeffaf anahtar kelime eşlemesi (tüm semboller için aynı — kripto
        # geneli haber akışı, sembole özel değil, tıpkı fear&greed gibi).
        from market_data.sentiment.news_tone_provider import fetch_news_tone
        real_news_tone = fetch_news_tone()

        # Faz 230: kullanıcı isteği — sosyal medya sentiment hâlâ dürüstçe
        # yapılmamıştı (Reddit'in kimliksiz API'si 403 veriyor). Kullanıcı
        # kendi ücretsiz Reddit "script" uygulama kaydını yaptıysa
        # (REDDIT_CLIENT_ID/SECRET) gerçek veri; yapmadıysa None -> 0.0
        # (nötr) varsayılana düşer, uydurulmaz.
        from market_data.sentiment.reddit_provider import fetch_social_sentiment
        real_social_sentiment = fetch_social_sentiment()

        return SentimentContext(
            fear_greed_index=self._get(ctx, "fear_greed_index", real_fgi if real_fgi is not None else 50.0),
            social_media_sentiment=self._get(
                ctx, "social_media_sentiment", real_social_sentiment if real_social_sentiment is not None else 0.0
            ),
            news_tone=self._get(ctx, "news_tone", real_news_tone if real_news_tone is not None else "neutral"),
            positioning=self._get(ctx, "positioning", real_positioning if real_positioning is not None else "neutral"),
        )

    def _real_onchain_metrics(self, symbol: str) -> dict:
        """Faz 196: SADECE gerçekten kolay/dürüst ölçülen metrikler —
        exchange akışı/whale/MVRV kasıtlı olarak burada yok (indexer
        gerektirir, icat edilmedi). Sadece kripto sembolleri için; ağ
        hatası olursa (provider zaten None döner) sessizce atlanır, hiçbir
        sayı uydurulmaz."""
        if not symbol.upper().endswith(("USDT", "BUSD", "USDC", "FDUSD")):
            return {}

        from database.repositories.onchain_snapshot_repository import OnChainSnapshotRepository
        from database.session_factory import SessionFactory
        from market_data.onchain.onchain_provider import (
            fetch_eth_gas_price_gwei,
            fetch_hash_rate_trend,
            fetch_network_activity_trend,
            fetch_solana_tps,
            fetch_usdt_total_supply,
        )

        result: dict = {}

        gas_price = fetch_eth_gas_price_gwei()
        if gas_price is not None:
            result["eth_gas_price_gwei"] = gas_price

        tps = fetch_solana_tps()
        if tps is not None:
            result["solana_tps"] = tps

        supply = fetch_usdt_total_supply()
        if supply is not None:
            with SessionFactory.get_session() as session:
                repo = OnChainSnapshotRepository(session)
                delta = repo.get_delta_24h("usdt_total_supply", supply)
                repo.save("usdt_total_supply", supply)
            if delta is not None:
                result["stablecoin_mint_24h"] = delta

        # Faz 215: eth_gas_price/solana_tps zaten TÜM kripto sembolleri
        # için "genel piyasa koşulu" olarak kullanılıyordu (chain-özel
        # değil) — aynı desenle, Bitcoin ağ sağlığı trendleri de genel
        # bir kripto piyasası göstergesi olarak ekleniyor.
        activity = fetch_network_activity_trend()
        if activity is not None:
            result["network_activity_trend"] = activity

        hash_rate = fetch_hash_rate_trend()
        if hash_rate is not None:
            result["hash_rate_trend"] = hash_rate

        return result

    def to_onchain(self, ctx: CognitiveCycleContext) -> OnChainContext:
        real_metrics = self._real_onchain_metrics(ctx.market.symbol or "")
        return OnChainContext(
            exchange_outflow_24h=self._get(ctx, "exchange_outflow_24h", 0.0),
            exchange_inflow_24h=self._get(ctx, "exchange_inflow_24h", 0.0),
            whale_accumulation=self._get(ctx, "whale_accumulation", False),
            whale_distribution=self._get(ctx, "whale_distribution", False),
            stablecoin_mint_24h=self._get(
                ctx, "stablecoin_mint_24h", real_metrics.get("stablecoin_mint_24h", 0.0)
            ),
            mvrv_zscore=self._get(ctx, "mvrv_zscore", 0.0),
            eth_gas_price_gwei=real_metrics.get("eth_gas_price_gwei"),
            solana_tps=real_metrics.get("solana_tps"),
            network_activity_trend=self._get(
                ctx, "network_activity_trend", real_metrics.get("network_activity_trend", "stable")
            ),
            hash_rate_trend=self._get(
                ctx, "hash_rate_trend", real_metrics.get("hash_rate_trend", "stable")
            ),
            symbol=ctx.market.symbol or "",
        )

    def _latest_external_signal(self, symbol: str, max_age_seconds: float = 1800.0):
        """Faz 193: TradingView webhook alarmları event-driven'dır (sürekli
        akmaz) — bu yüzden eski bir alarmı hâlâ geçerliymiş gibi kullanmamak
        için 30 dakikadan eski olanlar yok sayılır. Serbest metin formatı
        (Pine Script'in ne yazdığına bağlı) basit anahtar kelime eşlemesiyle
        bullish/bearish'e normalize ediliyor; tanınmayan bir format icat
        edilmez, sadece None döner."""
        if not symbol:
            return None, None
        from database.repositories.external_signal_repository import ExternalSignalRepository
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            row = ExternalSignalRepository(session).get_latest_for_symbol(symbol)

        if not row:
            return None, None

        signal_time = row.get("time")
        if signal_time is not None:
            now = datetime.now(UTC)
            if signal_time.tzinfo is None:
                age = (now.replace(tzinfo=None) - signal_time).total_seconds()
            else:
                age = (now - signal_time).total_seconds()
            if age > max_age_seconds:
                return None, None

        raw = (row.get("signal") or "").lower()
        if any(k in raw for k in ("buy", "long", "bull")):
            return "bullish", row.get("source")
        if any(k in raw for k in ("sell", "short", "bear")):
            return "bearish", row.get("source")
        return None, None

    def _correlated_market_trend(self, symbol: str) -> str | None:
        """Faz 194: "kripto Nasdaq/S&P500 ile korele gidiyor" — ikisinin de
        EN SON analiz edilmiş, gerçek trend'i aynı yöndeyse (sadece ikisi
        de bullish ya da ikisi de bearish) bir korelasyon sinyali üretir.
        Sadece kripto sembolleri için; endeksler henüz hiç analiz
        edilmediyse (fresh deploy) ya da anlaşmıyorlarsa None döner —
        icat edilmiş bir "zayıf sinyal" değil."""
        if not symbol.upper().endswith(("USDT", "BUSD", "USDC", "FDUSD")):
            return None

        from database.repositories.decision_persistor import DecisionPersistor
        from database.session_factory import SessionFactory

        trends = []
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            for index_symbol in ("^IXIC", "^GSPC"):
                rows = repo.get_by_symbol(index_symbol, limit=1)
                if not rows:
                    continue
                for contrib in (rows[0].get("agent_contributions") or []):
                    if isinstance(contrib, dict) and contrib.get("type") == "market_snapshot":
                        trend = (contrib.get("data", {}).get("features") or {}).get("trend")
                        if trend:
                            trends.append(trend)
                        break

        if len(trends) < 2:
            return None
        if all(t == "bullish" for t in trends):
            return "bullish"
        if all(t == "bearish" for t in trends):
            return "bearish"
        return None

    def to_technical(self, ctx: CognitiveCycleContext) -> TechnicalContext:
        symbol = ctx.market.symbol or ""
        external_signal, external_signal_source = self._latest_external_signal(symbol)
        correlated_market_trend = self._correlated_market_trend(symbol)
        return TechnicalContext(
            trend=self._get(ctx, "trend", "neutral"),
            momentum=self._get(ctx, "momentum", "neutral"),
            market_structure=self._get(ctx, "market_structure", "neutral"),
            volume_confirmation=self._get(ctx, "volume_confirmation", False),
            # Kritik bulgu (2026-08-05): "RSI" (büyük harf) burada zaten
            # kod tabanının genel konvansiyonuyla (CognitiveBinder,
            # inner_critic.py, outcome_evaluator.py, salience_detector.py,
            # onlarca test — hepsi "RSI") tutarlıydı. Asıl kırık taraf
            # services/orchestrator.py'nin "rsi" (küçük harf) yazması idi —
            # bu yüzden TechnicalAgent üretimde HİÇBİR ZAMAN gerçek RSI
            # görmedi, hep 50.0 varsayılanı kullandı. Düzeltme orada.
            rsi_value=self._get(ctx, "RSI", 50.0),
            ema_alignment=self._get(ctx, "ema_alignment", "neutral"),
            volatility_regime=self._get(ctx, "volatility_regime", "normal"),
            external_signal=external_signal,
            external_signal_source=external_signal_source,
            correlated_market_trend=correlated_market_trend,
            bollinger_percent_b=self._get(ctx, "bollinger_percent_b", 0.5),
            bollinger_bandwidth=self._get(ctx, "bollinger_bandwidth", 0.0),
            vwap_deviation_pct=self._get(ctx, "vwap_deviation_pct", 0.0),
            adx=self._get(ctx, "adx", 0.0),
            di_plus=self._get(ctx, "di_plus", 0.0),
            di_minus=self._get(ctx, "di_minus", 0.0),
            obv_trend=self._get(ctx, "obv_trend", "flat"),
            price_obv_divergence=self._get(ctx, "price_obv_divergence", "none"),
        )

    def to_pattern(self, ctx: CognitiveCycleContext) -> PatternContext:
        return PatternContext(
            structure_phase=self._get(ctx, "structure_phase", "neutral"),
            break_of_structure=self._get(ctx, "break_of_structure", "none"),
            change_of_character=self._get(ctx, "change_of_character", False),
            fair_value_gap=self._get(ctx, "fair_value_gap", "none"),
            swing_structure=self._get(ctx, "swing_structure", "mixed"),
            liquidity_sweep=self._get(ctx, "liquidity_sweep", "none"),
            fibonacci_nearest_level=self._get(ctx, "fibonacci_nearest_level", "none"),
            fibonacci_price_position=self._get(ctx, "fibonacci_price_position", "none"),
            wyckoff_event=self._get(ctx, "wyckoff_event", "none"),
        )

    def to_quant(self, ctx: CognitiveCycleContext) -> QuantContext:
        return QuantContext(
            zscore=self._get(ctx, "zscore", 0.0),
            realized_vol_percentile=self._get(ctx, "realized_vol_percentile", 50.0),
            autocorrelation=self._get(ctx, "autocorrelation", 0.0),
            hurst_exponent=self._get(ctx, "hurst_exponent", 0.5),
            long_term_trend_regime=self._get(ctx, "long_term_trend_regime", "insufficient_data"),
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
        imbalance, spread_bps, aggressive_buy_ratio = 0.0, 0.0, 0.5
        if symbol:
            with SessionFactory.get_session() as session:
                snapshot = MarketDataRepository(session).get_latest_order_book_snapshot(DataSource.BINANCE, symbol)
                if snapshot:
                    imbalance = snapshot["imbalance"]
                    spread_bps = snapshot["spread_bps"]
                    # Faz 214: gerçek bulgu — burası hep sabit 0.5 (tam
                    # nötr) kullanıyordu, hiçbir gerçek veri kaynağı yoktu.
                    # Artık ingest_order_book_task'ın Binance'in gerçek son
                    # işlemlerinden (isBuyerMaker) hesapladığı gerçek oranı
                    # okuyor — henüz hiç ingest edilmemişse (None) dürüstçe
                    # nötr varsayılana düşüyor.
                    if snapshot.get("aggressive_buy_ratio") is not None:
                        aggressive_buy_ratio = snapshot["aggressive_buy_ratio"]

        return OrderFlowContext(
            bid_ask_imbalance=self._get(ctx, "bid_ask_imbalance", imbalance),
            spread_bps=self._get(ctx, "spread_bps", spread_bps),
            aggressive_buy_ratio=self._get(ctx, "aggressive_buy_ratio", aggressive_buy_ratio),
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
