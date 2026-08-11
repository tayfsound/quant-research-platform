"""End-to-end cognitive loop orchestrator — v1.1 trusted paper cycle."""
from typing import Any
from database.repositories.app_settings_repository import TRADE_HORIZON_TO_RISK_TIMEFRAME
from database.repositories.risk_limit_repository import load_active_limits
from services.risk_state import load_position_risk_state
from market_data.ingestion.data_provider import get_ohlcv_provider, OHLCVProvider
from market_data.features.signal_engine import (
    compute_daily_atr_pct,
    compute_pattern_signals,
    compute_quant_signals,
    compute_technical_signals,
)
from simulator.fill_engine import FillEngine
from ml.training.replay_memory import ReplayMemory
from services.cognitive_engine import CognitiveEngine
from services.forward_outcome import ForwardOutcome
from services.decision_recorder import DecisionRecorder
from config import get_settings
from contracts.context import CognitiveCycleContext

import time

# Faz 255 performans düzeltmesi: kritik bulgu — canlıda doğrulandı. Risk
# ölçeklendirmesi için kullanılan bar'ları HER trading cycle'da (120s'de
# bir), HER sembol için yeniden çekmek gerçek bir performans regresyonuna
# yol açtı — her cycle sembol başına bir EK Binance isteği eklendi, bu da
# cycle süresini uzatıp trading_cycle sağlık kontrolünün "unhealthy"
# (dakikalarca bayat) düşmesine sebep oldu. Bu bar'lar (1d/4h) zaten
# yavaş değişen bir ölçü — 120 saniyede bir tazelenmesinin hiçbir anlamı
# yok. 15 dakikalık önbellek, riski gerçekçi tutarken gereksiz API
# yükünü ~7x azaltıyor.
_RISK_BARS_CACHE: dict[tuple[str, str], tuple[float, list]] = {}
_RISK_BARS_CACHE_TTL_SECONDS = 900


def _get_risk_bars_cached(data_provider, symbol: str, timeframe: str = "1d", limit: int = 30) -> list:
    now = time.time()
    key = (symbol, timeframe)
    cached = _RISK_BARS_CACHE.get(key)
    if cached and (now - cached[0]) < _RISK_BARS_CACHE_TTL_SECONDS:
        return cached[1]
    bars = data_provider.get_ohlcv(symbol, timeframe, limit=limit) or []
    _RISK_BARS_CACHE[key] = (now, bars)
    return bars


def _get_daily_bars_cached(data_provider, symbol: str) -> list:
    """Orta-vadeli katman (propose_medium_term) için gerçek günlük bar —
    kısa-vadeli katman artık _get_risk_bars_cached(..., timeframe="4h")
    kullanıyor, bkz. Faz 262 notu."""
    return _get_risk_bars_cached(data_provider, symbol, timeframe="1d")


def build_cognitive_context(
    symbol: str,
    timeframe: str,
    data,
    daily_data=None,
    timeframe_filter: str | None = None,
    exclude_timeframe: str | None = None,
    capital_pct_override: float | None = None,
    max_concurrent_override: int | None = None,
) -> CognitiveCycleContext:
    """Faz 224 review bulgusu (E): bu mantık önceden HEM burada (özel
    _build_context metodu olarak) HEM DE api/rest/cognitive.py'de
    (run_cognitive_cycle içinde) bağımsızca tekrarlanıyordu — "gap #15 ile
    aynı desen: iki entrypoint aynı işi bağımsız yapıyor, biri
    düzeltilince diğeri unutulabiliyor" (Faz 214'ün kendi yorumu, gerçek
    bir örneği: proposed_size düzeltmesi orchestrator.py'de yapılıp
    cognitive.py'de unutulmuştu). Artık TEK gerçek kaynak — her iki
    entrypoint de bunu çağırıyor."""
    ctx = CognitiveCycleContext()
    ctx.market.symbol = symbol
    ctx.market.timeframe = timeframe

    # Kritik bulgu (2026-08-05): buradan sadece ham rsi/ema/macd sayıları
    # geçiyordu — TechnicalAgent'ın gerçekten skorladığı trend/momentum/
    # market_structure/ema_alignment/volatility_regime alanlarını HİÇBİR
    # kod üretmiyordu (hep varsayılan/nötr), ve Pattern/Quant ajanları da
    # (bu oturumda eklenen) üretimde tamamen kör çalışıyordu. Artık
    # gerçek OHLCV geçmişinden hesaplanıyor — bkz. market_data/features/
    # signal_engine.py.
    technical_signals = compute_technical_signals(data)
    pattern_signals = compute_pattern_signals(data)
    quant_signals = compute_quant_signals(data)

    ctx.market.features = {**technical_signals, **quant_signals}
    # Faz 251: kullanıcı kararı — risk (stop/target) ölçeklendirmesi sinyal
    # zaman diliminden (genelde 1m, gürültü seviyesinde ATR) bağımsız,
    # daha yavaş bir bar setinden türetiliyor (bkz. signal_engine.
    # compute_daily_atr_pct üstündeki not — fonksiyon adı "günlük" ama
    # herhangi bir bar listesi üzerinde çalışır). Faz 262: kısa-vadeli
    # katman (orchestrator.propose) artık buraya 4 saatlik bar veriyor
    # ("scalp" niyetine uygun, saatler-günler içinde sonuçlanan mesafe),
    # orta-vadeli katman (propose_medium_term) gerçek günlük bar veriyor
    # ("sabırlı, nadir, büyük" profil) — aynı feature adı ("daily_atr_pct"),
    # farklı çağıranlar farklı kaynak veriyor. daily_data verilmezse ya da
    # yetersizse None kalır — RiskTargetStage bu durumda fail-closed
    # davranır (stop/target set etmez, DecisionFusion zaten yönlü olmayan/
    # eksik bir kararı WAIT'e çevirir).
    if daily_data:
        ctx.market.features["daily_atr_pct"] = compute_daily_atr_pct(daily_data)
    ctx.market.raw_snapshot = {
        "close": data[-1].close,
        "volume": data[-1].volume,
        "high": data[-1].high,
        "low": data[-1].low,
        **pattern_signals,
    }
    # Gap #15: bu alan önceden boş bir dict'ti, bu yüzden RiskEngine her
    # cycle'ı MISSING_LIMIT ile reddediyordu.
    ctx.risk.limits = load_active_limits()

    # Faz 188: test/live modu + gerçek açık pozisyon sayısı/sermaye
    # yüzdesi — RiskEngine (ön) ve RiskGateStage (son) bunları kullanıyor.
    # Faz 259: orta-vadeli katman kısa-vadeliyle aynı sermaye/pozisyon
    # sayacını paylaşmasın diye (bkz. services/risk_state.py docstring).
    risk_state = load_position_risk_state(
        symbol=symbol,
        timeframe_filter=timeframe_filter,
        exclude_timeframe=exclude_timeframe,
        capital_pct_override=capital_pct_override,
        max_concurrent_override=max_concurrent_override,
    )
    ctx.risk.trading_mode = risk_state["trading_mode"]
    ctx.risk.open_position_count = risk_state["open_position_count"]
    ctx.risk.max_concurrent_positions = risk_state["max_concurrent_positions"]
    ctx.risk.capital_used_pct = risk_state["capital_used_pct"]
    ctx.risk.max_capital_pct = risk_state["max_capital_pct"]
    ctx.risk.seconds_since_last_trade = risk_state["seconds_since_last_trade"]
    ctx.risk.min_seconds_between_trades = risk_state["min_seconds_between_trades"]
    ctx.risk.ai_enabled = risk_state["ai_enabled"]

    # Faz 211: her işlem, sermayenin (starting_capital * max_capital_pct)
    # eşit dilimlere bölünmüş (max_concurrent_positions) GERÇEK bir $
    # notional bütçesi hedefliyor; birim sayısı bu bütçenin güncel fiyata
    # bölünmesiyle çıkıyor — pahalı/ucuz varlıklar artık aynı gerçek $
    # riskini taşıyor.
    current_price = data[-1].close
    capital_per_trade = (
        risk_state["starting_capital"] * risk_state["max_capital_pct"]
        / max(risk_state["max_concurrent_positions"], 1)
    )
    ctx.decision.proposed_size = capital_per_trade / current_price if current_price else 0.0

    return ctx


class CognitiveOrchestrator:
    def __init__(
        self,
        data_provider: OHLCVProvider | None = None,
        max_position_size: float = 1.0,
        max_drawdown: float = 0.15,
        current_drawdown: float = 0.0,
    ):
        self.engine = CognitiveEngine()
        self.fill_engine = FillEngine()
        self.memory = ReplayMemory(capacity=10000)
        self.forward = ForwardOutcome(bars_forward=10)
        self.recorder = DecisionRecorder()
        self.data_provider = data_provider or get_ohlcv_provider()
        self.max_position_size = max_position_size
        self.max_drawdown_limit = max_drawdown
        self.current_drawdown = current_drawdown

    def propose(self, symbol: str) -> dict | None:
        """Faz 199: 'öner ama henüz açma' — services/portfolio_fusion.py'yi
        gerçekten bağlamak için run_cycle()'dan ayrıldı. Birden fazla
        sembolün eşzamanlı önerisini GERÇEKTEN açmadan önce portföy-seviyesi
        VaR'a göre ölçeklendirebilmek gerekiyor (bkz. run_portfolio_aware_
        cycle) — run_cycle() hâlâ tek-sembol, anında-finalize eski
        davranışını koruyor, regresyon yok."""
        # Faz 214: kullanıcı isteği — mum aralığı/geçmiş pencere artık
        # sabit değil, app_settings'ten okunuyor (varsayılan öncekiyle
        # birebir aynı: 1m, 100 bar — regresyon yok).
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            timeframe = settings_repo.get("candle_timeframe")
            lookback = int(settings_repo.get("candle_lookback"))
            # Faz 259: orta-vadeli katman devredeyse, kısa-vadeli katman
            # kendi sermaye/pozisyon sayacından o katmanın pozisyonlarını
            # hariç tutmalı — ikisi aynı kapasiteyi paylaşmasın diye
            # (bkz. services/risk_state.py).
            medium_term_enabled = settings_repo.get("medium_term_enabled") == "true"
            medium_term_timeframe = settings_repo.get("medium_term_timeframe")
            # Faz 265 — kullanıcı isteği: "İşlem vadesi" (Scalp/Gün içi/
            # Swing) artık hiçbir şeyi zorla kapatmıyor (Faz 215) ama YİNE
            # DE gerçek bir anlamı olsun istedi — artık kısa-vadeli
            # katmanın risk (stop/hedef) tabanını hangi bar aralığından
            # aldığını seçiyor. Dar taban (1h) = küçük mesafe = saatler
            # içinde sonuçlanma eğilimi ("scalp"); geniş taban (1d) =
            # büyük mesafe = günler/haftalar ("swing") — ama hiçbiri süre
            # yüzünden zorla kapatılmıyor, sadece gerçekten ulaşınca.
            trade_horizon = settings_repo.get("trade_horizon")

        data = self.data_provider.get_ohlcv(symbol, timeframe, limit=lookback)
        if not data:
            return None

        # Faz 262/265: risk (stop/hedef) tabanı artık trade_horizon'a göre
        # seçilen bar aralığından geliyor — aynı 1:4 oran (kalibrasyon için
        # hâlâ gerekli, bkz. RiskTargetStage) artık kullanıcının seçtiği
        # ölçeğe uygulanıyor. Orta-vadeli katman (propose_medium_term) hâlâ
        # gerçek günlük bar kullanıyor — "sabırlı, nadir, büyük" profil
        # orada kalmalı, bu ayardan etkilenmiyor.
        risk_timeframe = TRADE_HORIZON_TO_RISK_TIMEFRAME.get(trade_horizon, "4h")
        risk_data = _get_risk_bars_cached(self.data_provider, symbol, timeframe=risk_timeframe, limit=60)

        ctx = self._build_context(
            symbol,
            timeframe,
            data,
            daily_data=risk_data,
            exclude_timeframe=medium_term_timeframe if medium_term_enabled else None,
        )
        ctx = self.engine.run(ctx, persist=False)

        market_price = data[-1].close
        direction = ctx.decision.proposed_direction if ctx.decision.proposed_direction else "NEUTRAL"
        size = ctx.decision.final_size if ctx.decision.final_size else 0.0

        if direction != "NEUTRAL" and size > 0:
            result = self.fill_engine.simulate({"direction": direction, "size": size}, market_price)
            filled_price, fee = result.filled_price, result.fee
        else:
            filled_price, fee = market_price, 0.0

        # Faz 187: filled_price'ı ctx'e yaz ki RecordingStage (finalize()
        # içinde) gerçek entry_price'ı persist edebilsin.
        ctx.decision.filled_price = filled_price

        return {"ctx": ctx, "data": data, "fee": fee, "direction": direction}

    def propose_medium_term(self, symbol: str) -> dict | None:
        """Faz 259: kullanıcı isteği — "predictions WAIT döndüğünde uygun
        zamanda ai büyük pozisyonlara girsin, orta vadeli, günler/haftalar
        sürecek işlemlere... daha temkinli daha sakin yaklaşan fakat
        harekete geçtiğinde büyük oynayan bir yapı." Kısa-vadeli propose()
        ile AYNI CognitiveEngine/9-ajan konseyini kullanır — sadece sinyal
        verisi kısa-vadelinin candle_timeframe'i (genelde dakikalar)
        yerine kullanıcının seçtiği günlük/4 saatlik bardan geliyor, ve
        sermaye/pozisyon sayacı kısa-vadeliden tamamen ayrı (timeframe_
        filter/capital_pct_override/max_concurrent_override — bkz.
        services/risk_state.py). "WAIT döndüğünde" kısıtı burada
        UYGULANMIYOR — bu katman kendi bağımsız sinyaliyle çalışıyor,
        kısa-vadeli katmanın o an ne dediğine bakmıyor (ikisi zaten farklı
        zaman dilimlerinden farklı sinyaller üretiyor, birbirini
        bilerek/isteyerek bloke etmesi gerekmiyor)."""
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            if settings_repo.get("medium_term_enabled") != "true":
                return None
            timeframe = settings_repo.get("medium_term_timeframe")
            capital_pct = float(settings_repo.get("medium_term_capital_pct"))
            max_concurrent = int(settings_repo.get("medium_term_max_concurrent"))
            lookback = int(settings_repo.get("candle_lookback"))

        data = self.data_provider.get_ohlcv(symbol, timeframe, limit=lookback)
        if not data:
            return None

        # Sinyal zaten günlük/4h'den geliyor ama RiskTargetStage risk
        # ölçeklendirmesini HER ZAMAN gerçek günlük ATR'den yapıyor (bkz.
        # build_cognitive_context üstündeki not) — timeframe zaten "1d"
        # ise aynı barları tekrar çekmeye gerek yok.
        daily_data = data if timeframe == "1d" else _get_daily_bars_cached(self.data_provider, symbol)

        ctx = self._build_context(
            symbol,
            timeframe,
            data,
            daily_data=daily_data,
            timeframe_filter=timeframe,
            capital_pct_override=capital_pct,
            max_concurrent_override=max_concurrent,
        )
        ctx = self.engine.run(ctx, persist=False)

        market_price = data[-1].close
        direction = ctx.decision.proposed_direction if ctx.decision.proposed_direction else "NEUTRAL"
        size = ctx.decision.final_size if ctx.decision.final_size else 0.0

        if direction != "NEUTRAL" and size > 0:
            result = self.fill_engine.simulate({"direction": direction, "size": size}, market_price)
            filled_price, fee = result.filled_price, result.fee
        else:
            filled_price, fee = market_price, 0.0

        ctx.decision.filled_price = filled_price

        return {"ctx": ctx, "data": data, "fee": fee, "direction": direction}

    def run_medium_term_cycle(self, symbols: list[str], seed: int = 42) -> list[dict[str, Any]]:
        """Faz 259: portföy VaR füzyonu (run_portfolio_aware_cycle) kasıtlı
        olarak burada YOK — orta-vadeli katman zaten ayrı bir sermaye
        havuzunda, kısa-vadelinin korelasyon/VaR hesabına karışması ekstra
        bir karmaşıklık, ilk sürümde gerekli değil."""
        results = []
        for sym in symbols:
            p = self.propose_medium_term(sym)
            if p is None:
                results.append({"symbol": sym, "direction": "NEUTRAL", "error": "no_data_or_disabled"})
                continue
            results.append(self.finalize_proposal(p, seed=seed))
        return results

    def finalize_proposal(self, proposal: dict, seed: int = 42) -> dict[str, Any]:
        """propose()'un çıktısını (portföy fusion varsa ctx.decision.
        final_size değişmiş olabilir) al, gerçekten kaydet/aç. run_cycle()
        ile aynı sözlük şeklini döndürür."""
        ctx = proposal["ctx"]
        data = proposal["data"]
        fee = proposal["fee"]
        direction = proposal["direction"]
        filled_price = ctx.decision.filled_price
        size = ctx.decision.final_size or 0.0

        # Faz 268t — kritik bulgu: bu anlık "n-bar forward" hesaplaması
        # ÖNCEDEN iki amaca hizmet ediyordu — ctx.outcome (TradeOutcome)
        # CognitiveEngine.finalize()'ın memory_engine'i tetiklemesi için
        # okunuyordu. Faz 268j (episodic hafızanın sahte ForwardOutcome
        # ile kirlenmesini kapatan düzeltme) finalize()'daki memory_engine.
        # execute(ctx) çağrısını kaldırdığından beri ctx.outcome'ın TEK
        # okuyucusu gitti — artık hiçbir yerde okunmuyor (doğrulandı: grep
        # ile RecordingStage/_persist_and_learn/finalize()'ın hiçbiri
        # ctx.outcome'a bakmıyor). `outcome` (yerel değişken, ctx.outcome
        # DEĞİL) hâlâ gerçek bir tüketicisi olan ReplayMemory (self.memory.
        # add, aşağıda) için hesaplanmaya devam ediyor — o yüzden
        # self.forward.calculate() çağrısının kendisi silinmedi, sadece
        # artık hiç okunmayan ctx.outcome=TradeOutcome(...) ataması
        # kaldırıldı.
        #
        # decisions.status/entry_price/exit_price/opened_at/closed_at,
        # Faz 187'nin GERÇEK, zaman-bazlı pozisyon yaşam döngüsü — bu
        # yukarıdaki n-bar proxy'den kasıtlı olarak bağımsız: decisions.
        # outcome kolonu kayıt anında hep boş kalır (DecisionRecorder),
        # pozisyon gerçekten services/position_closer.py ile kapanana
        # kadar.
        outcome = self.forward.calculate(filled_price, direction, data)
        pnl = outcome["pnl"] - fee
        win = outcome["win"]

        # Memory (sadece risk-onaylı)
        ctx = self.engine.finalize(ctx)

        if direction != "NEUTRAL" and size > 0:
            self.memory.add({
                "decision_id": f"cycle_{seed}",
                "features": ctx.market.features,
                "label": 1 if win else 0,
                "pnl": pnl,
                "quality_score": 0.8,
                "timestamp": data[-1].timestamp.isoformat(),
                "direction": direction,
            })

        return {
            "direction": direction,
            "size": size,
            "filled_price": filled_price,
            "fee": fee,
            "pnl": pnl,
            "win": win,
            "memory_size": len(self.memory.memory),
            "risk_verdict": ctx.risk.evaluation.verdict if ctx.risk.evaluation else "unknown",
            # Faz 268x — kullanıcı bulgusu: Predictions sayfasında "Risk
            # Verdict" altında code='...' message='...' severity='...'
            # gibi ham Pydantic __str__() çıktısı görünüyordu — str(r)
            # RiskReason nesnesinin kendisini stringe çeviriyordu, insan
            # tarafından okunabilir bir mesaj değil. Sadece gerçek mesajı
            # (kod öneki ile, hangi kural olduğu belli olsun diye) veriyoruz.
            "risk_reasons": (
                [f"{r.code}: {r.message}" for r in ctx.risk.evaluation.reasons]
                if ctx.risk.evaluation else []
            ),
            "action": ctx.decision.action.value if ctx.decision.action else "WAIT",
            "confidence": ctx.decision.confidence,
            "features": ctx.market.features,
            "symbol": ctx.market.symbol,
        }

    def run_portfolio_aware_cycle(self, symbols: list[str], seed: int = 42) -> list[dict[str, Any]]:
        """Faz 199: services/portfolio_fusion.py + risk/limits/portfolio.py'yi
        (yazılmış, test edilmiş ama hiçbir yerden çağrılmayan portföy VaR
        motoru) gerçekten bağlıyor. Aynı cycle'da 2+ sembol eşzamanlı yönlü
        öneri üretirse, GERÇEKTEN açılmadan önce gerçek kovaryans matrisiyle
        (korelasyon dahil) hesaplanan portföy VaR'ı kullanıcının belirlediği
        sınırı (max_portfolio_var_pct) aşarsa önerilen büyüklükler orantılı
        şekilde küçültülüyor — "sinyal limitleri gevşetemez" kuralı burada
        da geçerli, sadece küçültebiliyor."""
        proposals: dict[str, dict] = {}
        for sym in symbols:
            p = self.propose(sym)
            if p is not None:
                proposals[sym] = p

        directional = {
            sym: p for sym, p in proposals.items()
            if p["direction"] in ("LONG", "SHORT") and (p["ctx"].decision.final_size or 0) > 0
        }

        if len(directional) >= 2:
            self._apply_portfolio_fusion(directional)

        return [
            self.finalize_proposal(proposals[sym], seed=seed) if sym in proposals
            else {"symbol": sym, "direction": "NEUTRAL", "error": "no_data", "memory_size": len(self.memory.memory)}
            for sym in symbols
        ]

    def _apply_portfolio_fusion(self, directional: dict[str, dict]) -> None:
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory
        from risk.limits.portfolio import PortfolioRiskEngine
        from services.portfolio_fusion import PortfolioFusionStage

        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            starting_capital = float(settings_repo.get("starting_capital"))
            max_var_pct = float(settings_repo.get("max_portfolio_var_pct"))

        returns: dict[str, list[float]] = {}
        proposed_sizes: dict[str, float] = {}
        for sym, p in directional.items():
            closes = [bar.close for bar in p["data"]]
            rets = [
                (closes[i] - closes[i - 1]) / closes[i - 1]
                for i in range(1, len(closes)) if closes[i - 1]
            ]
            if len(rets) < 2:
                continue
            returns[sym] = rets
            sign = 1.0 if p["direction"] == "LONG" else -1.0
            proposed_sizes[sym] = sign * (p["ctx"].decision.final_size or 0.0)

        if len(returns) < 2:
            return

        min_len = min(len(v) for v in returns.values())
        returns = {s: v[-min_len:] for s, v in returns.items()}
        proposed_sizes = {s: v for s, v in proposed_sizes.items() if s in returns}

        fusion = PortfolioFusionStage(PortfolioRiskEngine())
        result = fusion.fuse(
            proposed_sizes=proposed_sizes,
            returns=returns,
            portfolio_value=starting_capital,
            max_var=starting_capital * max_var_pct,
        )

        if result.scaled_down:
            for sym, signed_size in result.final_sizes.items():
                directional[sym]["ctx"].decision.final_size = abs(signed_size)

    def _build_context(
        self,
        symbol: str,
        timeframe: str,
        data,
        daily_data=None,
        timeframe_filter: str | None = None,
        exclude_timeframe: str | None = None,
        capital_pct_override: float | None = None,
        max_concurrent_override: int | None = None,
    ) -> CognitiveCycleContext:
        # Faz 224 review (E): gövde module-level build_cognitive_context()'e
        # taşındı — api/rest/cognitive.py da artık AYNI fonksiyonu çağırıyor,
        # iki bağımsız kopya kalmadı.
        return build_cognitive_context(
            symbol,
            timeframe,
            data,
            daily_data=daily_data,
            timeframe_filter=timeframe_filter,
            exclude_timeframe=exclude_timeframe,
            capital_pct_override=capital_pct_override,
            max_concurrent_override=max_concurrent_override,
        )

    def run_cycle(self, seed: int = 42, symbol: str | None = None) -> dict[str, Any]:
        settings = get_settings()
        symbol = symbol or settings.DEFAULT_SYMBOL

        proposal = self.propose(symbol)
        if proposal is None:
            return {"direction": "NEUTRAL", "error": "no_data", "memory_size": len(self.memory.memory)}

        return self.finalize_proposal(proposal, seed=seed)
