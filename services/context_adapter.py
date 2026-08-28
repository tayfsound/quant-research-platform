"""Context Adapter — ham piyasa verisini ajan bağlamlarına dönüştürür."""
from datetime import UTC, datetime

from contracts.context import CognitiveCycleContext
from contracts.credit import CreditContext
from contracts.epistemology import EpistemologyContext
from contracts.macro import MacroContext
from contracts.onchain import OnChainContext
from contracts.order_flow import OrderFlowContext
from contracts.pattern import PatternContext
from contracts.quant import QuantContext
from contracts.relative_strength import RelativeStrengthContext
from contracts.sentiment import SentimentContext
from contracts.technical import TechnicalContext
from contracts.time_context import TimeContext
from contracts.volatility import VolatilityContext

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
            fetch_net_liquidity_trend,
        )

        return MacroContext(
            inflation_trend=self._get(ctx, "inflation_trend", fetch_inflation_trend() or "stable"),
            liquidity_condition=self._get(ctx, "liquidity_condition", fetch_liquidity_condition() or "neutral"),
            central_bank_bias=self._get(ctx, "central_bank_bias", fetch_central_bank_bias() or "neutral"),
            employment_trend=self._get(ctx, "employment_trend", fetch_employment_trend() or "stable"),
            # Faz 267: kullanıcı isteği — hazine borç/likidite döngüsü.
            # fetch_net_liquidity_trend None dönerse (API/key yoksa)
            # dürüstçe boş string — macro_agent bunu "veri yok" sayıp
            # atlıyor, "stable" gibi icat edilmiş bir varsayılana düşmüyor
            # (diğer 4 alandan kasıtlı olarak farklı: onlar zaten var olan,
            # köklü sinyaller, bu yeni ve henüz doğrulanmamış).
            net_liquidity_trend=self._get(ctx, "net_liquidity_trend", fetch_net_liquidity_trend() or ""),
        )

    def to_sentiment(self, ctx: CognitiveCycleContext) -> SentimentContext:
        # Faz 367-devam — kullanıcı kararıyla geri getirildi (2026-08-28,
        # bkz. agents/sentiment_agent.py'nin başındaki not — Ajan
        # Kombinasyonu Güvenilirliği bunun DİĞER ajanlarla birlikte çok
        # güçlü olduğunu gösterdi).
        #
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

        # Faz 230: Reddit kapandı — Devvit politikası AI kullanımını
        # yasaklıyor (bkz. reddit_provider.py'nin docstring'i, proje
        # hafızası "project_reddit_sentiment_blocked" — kalıcı olarak
        # kapalı, alternatif kaynak henüz yok). Faz 268-sonrası eklenen
        # LLM tabanlı alternatif (llm_news_sentiment_provider.py) da
        # ayrıca kaldırıldığı için (Faz 364-367, "LLM kaldırma") artık
        # SADECE reddit_provider.py deneniyor — REDDIT_CLIENT_ID/SECRET
        # ayarlı değilse (varsayılan durum) dürüstçe None -> 0.0 (nötr)
        # düşülüyor, hiçbir zaman uydurulmuyor. Gerçek bir alternatif
        # bulununca burası güncellenecek.
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

    def to_credit(self, ctx: CognitiveCycleContext) -> CreditContext:
        # Faz 333: gerçek FRED verisi (T10Y2Y/BAMLH0A0HYM2) — MacroAgent'ın
        # net_liquidity_trend'iyle AYNI fail-closed desen: ağ hatası/key
        # yoksa provider None döner, dürüstçe boş string'e (agent'ın
        # atladığı "veri yok" durumu) düşülüyor — icat edilmiş bir varsayılan
        # değil.
        from market_data.macro.fred_provider import fetch_credit_spread_trend, fetch_yield_curve_signal

        return CreditContext(
            yield_curve_signal=self._get(ctx, "yield_curve_signal", fetch_yield_curve_signal() or ""),
            credit_spread_trend=self._get(ctx, "credit_spread_trend", fetch_credit_spread_trend() or ""),
        )

    def to_volatility(self, ctx: CognitiveCycleContext) -> VolatilityContext:
        # Faz 336: gerçek Deribit DVOL verisi — CreditAgent'ın FRED
        # entegrasyonuyla AYNI fail-closed desen.
        from market_data.volatility.deribit_provider import fetch_dvol_level, fetch_dvol_trend

        return VolatilityContext(
            dvol_level=self._get(ctx, "dvol_level", fetch_dvol_level()),
            dvol_trend=self._get(ctx, "dvol_trend", fetch_dvol_trend() or ""),
        )

    # Faz 367-devam — kullanıcı isteği: agents/onchain_agent.py'nin
    # exchange_outflow_24h > exchange_inflow_24h * 1.5 (ve tersi) karşılaştırması
    # İKİ AYRI (gross giriş, gross çıkış) büyüklük bekliyor ama DefiLlama
    # sadece NET bakiye deltasını verebiliyor (bkz. onchain_provider.py::
    # fetch_exchange_net_flow_24h_usd). Net'i "diğer taraf sıfır" olarak
    # dağıtmak, HER gün (bakiye $1 bile değişse) tetiklenen anlamsız bir
    # sinyale yol açardı — bu yüzden aynı büyüklük mertebesindeki
    # stablecoin_mint_24h eşiğiyle (>$100M) AYNI ilkeyle bir maddiyet
    # eşiği uygulanıyor: sadece gerçekten büyük bir net akışta (izlenen
    # borsaların toplam ~$230B tvl'sine göre anlamlı bir pay) alan
    # dolduruluyor, aksi halde 0.0 varsayılanı (sessiz) korunuyor.
    _EXCHANGE_FLOW_MATERIALITY_THRESHOLD_USD = 100_000_000

    def _real_onchain_metrics(self, symbol: str) -> dict:
        """Faz 196/268v/367-devam: gerçekten ölçülebilen metrikler.
        exchange_inflow/outflow artık GERÇEK veriyle besleniyor (bkz.
        onchain_provider.py::fetch_exchange_net_flow_24h_usd — DefiLlama'nın
        ücretsiz, kimliksiz CEX Transparency API'si). whale_accumulation/
        whale_distribution GEÇİCİ bir yaklaşımla besleniyor (bkz. onchain_
        provider.py::fetch_whale_like_exchange_flow — gerçek bireysel
        balina cüzdan takibi DEĞİL, ücretsiz katmanı olan bir sağlayıcı
        bulunamadı; TEK bir borsada orantısız yoğunlaşmış bir bakiye
        hareketi "balina benzeri" olarak yorumlanıyor, kullanıcı onayıyla).
        MVRV Z-Score
        Faz 268v'de eklendi (bitcoin-data.com, API key gerektirmiyor,
        gerçek veri). Sadece kripto sembolleri için; ağ hatası olursa
        (provider zaten None döner) sessizce atlanır, hiçbir sayı
        uydurulmaz."""
        if not symbol.upper().endswith(("USDT", "BUSD", "USDC", "FDUSD")):
            return {}

        from database.repositories.onchain_snapshot_repository import OnChainSnapshotRepository
        from database.session_factory import SessionFactory
        from market_data.onchain.onchain_provider import (
            fetch_eth_gas_price_gwei,
            fetch_exchange_net_flow_24h_usd,
            fetch_hash_rate_trend,
            fetch_mvrv_zscore,
            fetch_network_activity_trend,
            fetch_nupl,
            fetch_solana_tps,
            fetch_sopr,
            fetch_usdt_total_supply,
            fetch_whale_like_exchange_flow,
        )

        result: dict = {}

        # Faz 367-devam — kullanıcı kararı (2026-08-27): "balina" alanları
        # için gerçek bir cüzdan-takip API'si yok (bkz. onchain_provider.py'
        # nin fetch_whale_like_exchange_flow docstring'i — ücretsiz katmanı
        # olan hiçbir sağlayıcı bulunamadı), GEÇİCİ bir yaklaşım olarak
        # onaylandı: TEK bir borsada, diğerlerinden orantısız derecede
        # büyük/yoğunlaşmış bir bakiye hareketi. Pozitif delta (bakiye
        # ARTTI) = varlıklar borsaya taşınıyor = olası dağıtım/satış
        # niyeti; negatif (bakiye AZALDI) = borsadan soğuk cüzdana
        # çekiliyor = klasik biriktirme sinyali — agents/onchain_agent.py'
        # nin zaten beklediği AYNI anlam (bkz. kendi evidence metinleri).
        whale_like = fetch_whale_like_exchange_flow()
        if whale_like is not None:
            _, dominant_delta = whale_like
            if dominant_delta > 0:
                result["whale_distribution"] = True
            else:
                result["whale_accumulation"] = True

        net_flow = fetch_exchange_net_flow_24h_usd()
        if net_flow is not None and abs(net_flow) > self._EXCHANGE_FLOW_MATERIALITY_THRESHOLD_USD:
            if net_flow > 0:
                result["exchange_inflow_24h"] = net_flow
            else:
                result["exchange_outflow_24h"] = -net_flow

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

        # Faz 268v: kullanıcı isteği — MVRV Z-Score, network_activity_trend/
        # hash_rate_trend ile AYNI desende (Bitcoin'e özel, tüm kripto
        # sembollerine "genel piyasa koşulu" olarak uygulanan bir sinyal).
        mvrv = fetch_mvrv_zscore()
        if mvrv is not None:
            result["mvrv_zscore"] = mvrv

        # Faz 335 — kullanıcı bulgusu: NUPL/SOPR yazılmış ama hiç
        # bağlanmamıştı. mvrv_zscore ile AYNI desen (genel piyasa koşulu,
        # tüm kripto sembollerine uygulanıyor).
        nupl = fetch_nupl()
        if nupl is not None:
            result["nupl"] = nupl

        sopr = fetch_sopr()
        if sopr is not None:
            result["sopr"] = sopr

        return result

    def to_onchain(self, ctx: CognitiveCycleContext) -> OnChainContext:
        real_metrics = self._real_onchain_metrics(ctx.market.symbol or "")

        # Faz 300 — kullanıcı bulgusu: "Predictions'da onchain verileri
        # dönmüyor." Kök neden: gerçek onchain metrikleri SADECE burada
        # (OnchainAgent'a giden OnChainContext'e) hesaplanıyordu, ctx.
        # market.features'a HİÇ yazılmıyordu — macro/order_flow/vb. diğer
        # domain'lerle AYNI desen. Predictions.tsx (`/orchestrator/cycle`)
        # SADECE ctx.market.features'ı gösterdiği için bu veriler o sayfada
        # hiç görünmüyordu, sistem kararlarını etkilemesine RAĞMEN (gerçek
        # bir işlevsellik bug'ı değil, sadece bir görünürlük eksikliği).
        # onchain_ önekiyle (technical/quant feature adlarıyla çakışmasın
        # diye) ekleniyor — sadece EKLEME, mevcut hiçbir karar mantığı
        # değişmiyor.
        for key, value in real_metrics.items():
            ctx.market.features[f"onchain_{key}"] = value
        return OnChainContext(
            exchange_outflow_24h=self._get(
                ctx, "exchange_outflow_24h", real_metrics.get("exchange_outflow_24h", 0.0)
            ),
            exchange_inflow_24h=self._get(
                ctx, "exchange_inflow_24h", real_metrics.get("exchange_inflow_24h", 0.0)
            ),
            whale_accumulation=self._get(
                ctx, "whale_accumulation", real_metrics.get("whale_accumulation", False)
            ),
            whale_distribution=self._get(
                ctx, "whale_distribution", real_metrics.get("whale_distribution", False)
            ),
            stablecoin_mint_24h=self._get(
                ctx, "stablecoin_mint_24h", real_metrics.get("stablecoin_mint_24h", 0.0)
            ),
            mvrv_zscore=self._get(ctx, "mvrv_zscore", real_metrics.get("mvrv_zscore", 0.0)),
            eth_gas_price_gwei=real_metrics.get("eth_gas_price_gwei"),
            solana_tps=real_metrics.get("solana_tps"),
            nupl=real_metrics.get("nupl"),
            sopr=real_metrics.get("sopr"),
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
            higher_timeframe_trend=self._get(ctx, "higher_timeframe_trend", None),
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
        funding_rate = None
        open_interest_trend = "unknown"
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
                    # Faz 247-249: vadeli kontratı olmayan bir sembolde
                    # (fail-closed) None/"unknown" kalır.
                    if snapshot.get("funding_rate") is not None:
                        funding_rate = snapshot["funding_rate"]
                    if snapshot.get("open_interest_trend"):
                        open_interest_trend = snapshot["open_interest_trend"]

        return OrderFlowContext(
            bid_ask_imbalance=self._get(ctx, "bid_ask_imbalance", imbalance),
            spread_bps=self._get(ctx, "spread_bps", spread_bps),
            aggressive_buy_ratio=self._get(ctx, "aggressive_buy_ratio", aggressive_buy_ratio),
            funding_rate=self._get(ctx, "funding_rate", funding_rate),
            open_interest_trend=self._get(ctx, "open_interest_trend", open_interest_trend),
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

    def to_relative_strength(self, ctx: CognitiveCycleContext) -> RelativeStrengthContext:
        """Faz 242-243: bu sembolün son dönem getirisini DİĞER sembollerin
        ortalama getirisiyle karşılaştırır.

        Faz 268-sonrası — kullanıcı bulgusu: eskiden bu karşılaştırma
        SADECE ~49 sembollük watchlist içindeydi (market_snapshots
        tablosundan, 1 saatlik pencere) — kripto piyasası zaten yüksek
        korelasyonlu olduğu için bu neredeyse hiçbir zaman anlamlı bir
        ayrışma bulamıyordu ("Watchlist ortalamasından belirgin bir
        ayrışma yok" hep aynı sonuçtu). Kullanıcının kendi sözüyle:
        "Piyasadaki bütün coinleri görüp ona göre kıyaslama yapması
        lazım." Artık services/market_breadth.py ile Binance Futures'ın
        TÜM USDT-marjinli sözleşmeleri (yüzlerce sembol, tek önbelleklenmiş
        bulk çağrı) için gerçek 24 saatlik fiyat değişimi kullanılıyor —
        hem sembol hem havuz AYNI (24h) pencereden, gerçekten piyasa
        genelinde bir kıyaslama."""
        symbol = ctx.market.symbol or ""
        if not symbol:
            return RelativeStrengthContext()

        from market_data.ingestion.data_provider import looks_like_binance_pair

        if not looks_like_binance_pair(symbol):
            # Kripto olmayan (hisse/endeks/emtia) semboller için Binance
            # Futures'ta veri yok — icat edilmiş bir karşılaştırma yapılmaz.
            return RelativeStrengthContext()

        from services.market_breadth import fetch_market_wide_24h_returns

        returns = fetch_market_wide_24h_returns()
        symbol_return = returns.get(symbol)
        peer_returns = [r for s, r in returns.items() if s != symbol]

        if symbol_return is None or len(peer_returns) < 3:
            return RelativeStrengthContext(basket_size=len(peer_returns))

        basket_mean = sum(peer_returns) / len(peer_returns)
        return RelativeStrengthContext(
            symbol_return_pct=symbol_return,
            basket_mean_return_pct=basket_mean,
            basket_size=len(peer_returns),
            relative_strength_pct=symbol_return - basket_mean,
        )

    def to_epistemology(self, ctx: CognitiveCycleContext) -> EpistemologyContext:
        present = sum(1 for key in _EXPECTED_FEATURES if self._get(ctx, key, None) is not None)
        completeness = present / len(_EXPECTED_FEATURES)
        # Faz 268-sonrası — kritik bulgu, kullanıcı bulgusu: "her pozisyonda
        # AYNI süre (7200sn) bayat diyor" — gerçek işlem gecikmesi olsaydı
        # her seferinde farklı olurdu. Kök neden: order_book_snapshots.time
        # bug'ıyla (Faz 231) AYNI hata sınıfı — bu makinenin yerel saati
        # CEST/UTC+2. datetime.now() (naive, YEREL saat) ile ctx.timestamp'in
        # (aware, UTC) tzinfo'sunu SİLİP naive gibi karşılaştırmak, gerçek
        # geçen süreden BAĞIMSIZ, sabit +2 saatlik (7200sn) bir sahte yaş
        # üretiyordu — EpistemologyAgent'ın "veri bayat" uyarısı ve
        # freshness hesabı SİSTEMATİK OLARAK yanlıştı (veri aslında taze
        # olsa bile hep "2 saat bayat" görünüyordu).
        age_seconds = max(0.0, (datetime.now(UTC) - ctx.timestamp).total_seconds())

        return EpistemologyContext(
            feature_completeness=round(completeness, 3),
            data_age_seconds=age_seconds,
            known_unknown_count=len(_EXPECTED_FEATURES) - present,
            data_quality_score=self._get(ctx, "data_quality_score", 1.0),
            high_impact_event_imminent=bool(self._get(ctx, "high_impact_event_imminent", False)),
        )
