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
from config.settings import get_settings
from engines.cognitive_pipeline import RiskTargetStage
from engines.risk_engine import RiskEngine
from market_data.features.signal_engine import compute_daily_atr_pct
from market_data.ingestion.data_provider import RoutingProvider
from market_data.market_hours import is_market_open
from services.decision_recorder import DecisionRecorder
from services.risk_state import load_position_risk_state

# Faz 268-sonrası — kritik bulgu, kullanıcı bulgusu: eski LEG_SIZE=0.2
# SABİT BİR HAM VARLIK BİRİMİYDİ (dolar değil) — 0.2 BTC (~$13.000
# notional, 10x kaldıraçla) ile 0.2 ETH (~$380) arasında GERÇEK dolar
# riski 30 kattan fazla farklıydı, "sabit-küçük bir boyut" niyetinin tam
# tersiydi. Artık AppSettings'teki (kullanıcı ayarlanabilir)
# pairs_trading_leg_capital_usd kullanılıyor — current_price'a bölünüp
# asıl miktara çevriliyor, TÜM varlıklarda gerçekten aynı dolar boyutu.


class PairsTrader:
    def __init__(self, data_provider=None):
        self.data_provider = data_provider or RoutingProvider()
        self.recorder = DecisionRecorder()

    def check_and_trade_pairs(self) -> list[dict]:
        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            ai_enabled = settings_repo.get("ai_enabled") == "true"
            pairs_trading_enabled = settings_repo.get("pairs_trading_enabled") == "true"

        if not ai_enabled:
            return [{"skipped": "ai_disabled"}]

        # Faz 282 — kullanıcı kararı (2026-08-19): bacak-boyutu birim
        # bug'ı düzeltmesinden sonra açılan 2 temiz pozisyon görülünce,
        # strateji tamamen durduruldu — mevcut pozisyonlar normal stop/
        # hedefe göre kapanana kadar izlenmeye devam eder (PositionCloser
        # zaten kaynağından bağımsız TÜM açık pozisyonları kontrol ediyor),
        # sadece YENİ bacak açılmıyor.
        if not pairs_trading_enabled:
            return [{"skipped": "pairs_trading_disabled"}]

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
        entry_price = data[-1].close
        if not entry_price or entry_price <= 0:
            return False

        with SessionFactory.get_session() as session:
            leg_capital_usd = float(AppSettingsRepository(session).get("pairs_trading_leg_capital_usd"))

        ctx = CognitiveCycleContext()
        ctx.market.symbol = symbol
        ctx.market.raw_snapshot = {
            "close": entry_price,
            "pairs_trade": pair_label,
            "pairs_zscore": zscore,
        }
        ctx.decision.proposed_direction = direction
        # Faz 268-sonrası: dolar bazlı, TÜM varlıklarda gerçekten aynı
        # boyut — bkz. modül üstündeki not.
        ctx.decision.final_size = leg_capital_usd / entry_price
        ctx.decision.filled_price = entry_price

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
        ctx.risk.concept_drift_reason = risk_state["concept_drift_reason"]

        # Not: bu, bacağın kendi ATR'sine göre standart bir stop/hedef —
        # spread'in ortalamaya dönüşünü (asıl pairs trading çıkış sinyali)
        # takip eden ayrı bir mekanizma değil. Bilinçli bir sınırlama:
        # spread-farkındalıklı kapanış, PositionCloser'ın çift bacakları
        # birbirine bağlaması gerektirir — ayrı, daha büyük bir iş.
        #
        # Faz 268-sonrası — gerçek bulgu: eski kod sinyal-zaman-dilimi
        # (1m) ATR'sini DOĞRUDAN mesafe olarak kullanıyordu — Faz 251'in
        # RiskTargetStage için düzelttiği AYNI hata, burada hiç
        # düzeltilmemişti. Gerçek 20 hedge işleminde ölçülen stop mesafesi
        # %0.002-%0.069 arasındaydı (gürültü seviyesi — tek bir işlem
        # -$9595 kaybettirdi). Artık RiskTargetStage ile AYNI, doğrulanmış
        # mekanizma: günlük ATR yüzdesi + AppSettings'teki AYNI stop_atr_
        # mult/target_atr_mult/min_stop_pct (ayrı, hiç doğrulanmamış bir
        # oran icat etmek yerine).
        daily_bars = self.data_provider.get_ohlcv(symbol, "1d", limit=30)
        daily_atr_pct = compute_daily_atr_pct(daily_bars) if daily_bars else None
        if daily_atr_pct and daily_atr_pct > 0:
            stop_mult, target_mult, min_stop_pct = RiskTargetStage()._load_multipliers(direction)
            stop_pct = stop_mult * daily_atr_pct
            target_pct = target_mult * daily_atr_pct
            if stop_pct < min_stop_pct:
                scale = min_stop_pct / stop_pct
                stop_pct *= scale
                target_pct *= scale
            ctx.decision.stop_loss_distance = entry_price * stop_pct
            ctx.decision.take_profit_distance = entry_price * target_pct

        # Faz 268-sonrası — kritik bulgu, kullanıcı bulgusu: bu bacaklar
        # DecisionFusion'dan hiç geçmiyordu — ana AI'ın "hedef, komisyonu
        # karşılamayacak kadar küçükse açma" korumasını (min_profit_
        # target_pct) tamamen atlıyordu. Gerçek veride görüldü: bazı
        # hedge bacakları "take_profit"e ulaşıp yine de NET ZARARLA
        # kapandı (küçük hedef, round-trip komisyonu karşılamadı). Artık
        # AYNI kontrol burada da uygulanıyor.
        if ctx.decision.take_profit_distance:
            with SessionFactory.get_session() as session:
                min_profit_target_pct = float(AppSettingsRepository(session).get("min_profit_target_pct"))
            if ctx.decision.take_profit_distance / entry_price < min_profit_target_pct:
                return False

        # Faz 268-sonrası — gerçek bulgu: burada RiskEngine() secret'sız
        # çağrılıyordu (cognitive_engine.py/execution_router.py'nin
        # AKSİNE), gerçek imzalı risk_limits her zaman HASH_MISMATCH ile
        # reddediliyordu — hedge bacakları hiçbir zaman gerçekten
        # açılamıyordu (sadece hash boşken/dev modunda çalışıyordu).
        ctx = RiskEngine(secret=get_settings().SECRET_KEY).execute(ctx)
        if ctx.risk.evaluation.verdict != "approved":
            return False

        self.recorder.record(ctx)
        return True
