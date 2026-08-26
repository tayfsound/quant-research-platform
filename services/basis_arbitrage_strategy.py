"""Faz 344: Cross-Asset Arbitrage Engine v1 — Spot-Perpetual Basis
Arbitrajı (cash-and-carry).

Kullanıcı onayı: council'in oy/skorlama mantığından tamamen bağımsız,
mekanik bir strateji — pump_fade_strategy.py/pairs_trader.py ile AYNI
desen (kendi experiment_bucket'ı, kendi ayarları, RiskEngine'den geçiyor
ama DecisionFusion/MetaStage'i hiç görmüyor). Perpetual futures spot'a
göre PRİMLİ işlem görürken (pozitif basis) VE funding rate pozitifken:
SHORT perpetual + LONG spot açılır. Piyasa-nötr (yön riski teorik olarak
birbirini götürür) — kâr kaynağı: (1) SHORT taraf pozitif funding'de
tahsilat alır, (2) basis zamanla yakınsar.

Spot ve perpetual bacağı AYNI sembol string'iyle (ör. "BTCUSDT") temsil
ediliyor — sistemin geri kalanı zaten HER pozisyonu (kaldıraçlı olanlar
dahil) tek bir spot-fiyat kaynağından (RoutingProvider.get_ohlcv) izliyor,
bu strateji için ayrı bir futures-mark-price takip mekanizması icat
edilmiyor. `market_data/basis/binance_futures_provider.py`'nin
premiumIndex verisi SADECE giriş anındaki tetikleyici sinyal (basis/
funding) için kullanılıyor.

KRİTİK tasarım kararı: bacaklar pairs_trader'ın aksine standart bir ATR
stop/hedefle AYRI AYRI kapanmıyor — ikisi de AYNI varlıkta olduğu için
biri bağımsız kapanırsa kalan bacak "piyasa-nötr" değil ÇIPLAK yönlü bir
pozisyon haline gelir (asıl amacın tam tersi). Bunun yerine ikisi
BİRLİKTE, sadece maksimum tutma süresi (basis_arbitrage_max_hold_hours)
dolunca kapatılıyor — gerçek bir basis-yakınsama-farkında erken çıkış
ayrı, daha büyük bir iş (pairs_trader'ın kendi, zaten kabul edilmiş
sınırlamasıyla AYNI ilke)."""
from datetime import UTC, datetime

from config.settings import get_settings
from contracts.context import CognitiveCycleContext
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.repositories.risk_limit_repository import load_active_limits
from database.session_factory import SessionFactory
from engines.risk_engine import RiskEngine
from market_data.basis.binance_futures_provider import fetch_perp_basis
from market_data.ingestion.data_provider import RoutingProvider
from market_data.market_hours import is_market_open
from services.decision_recorder import DecisionRecorder
from services.position_closer import PositionCloser
from services.pump_fade_strategy import fetch_usdt_perpetual_symbols
from services.risk_state import load_position_risk_state

EXPERIMENT_BUCKET = "basis_arb_v1"


class BasisArbitrageStrategy:
    def __init__(self, data_provider=None):
        self.data_provider = data_provider or RoutingProvider()
        self.recorder = DecisionRecorder()

    def run_cycle(self) -> dict:
        with SessionFactory.get_session() as session:
            settings_repo = AppSettingsRepository(session)
            enabled = settings_repo.get("basis_arbitrage_enabled") == "true"
            if not enabled:
                return {"skipped": "basis_arbitrage_disabled"}

            min_basis_pct = float(settings_repo.get("basis_arbitrage_min_basis_pct"))
            min_funding_rate = float(settings_repo.get("basis_arbitrage_min_funding_rate"))
            leg_capital_usd = float(settings_repo.get("basis_arbitrage_leg_capital_usd"))
            max_open_pairs = int(settings_repo.get("basis_arbitrage_max_open_pairs"))

        symbols = fetch_usdt_perpetual_symbols()
        if not symbols:
            return {"skipped": "no_symbols"}

        opened = []
        for symbol in symbols:
            result = self._try_open_pair(symbol, min_basis_pct, min_funding_rate, leg_capital_usd, max_open_pairs)
            if result is not None:
                opened.append(result)

        return {"candidates_scanned": len(symbols), "opened_pairs": opened}

    def _try_open_pair(
        self, symbol: str, min_basis_pct: float, min_funding_rate: float,
        leg_capital_usd: float, max_open_pairs: int,
    ) -> dict | None:
        if not is_market_open(symbol):
            return None

        with SessionFactory.get_session() as session:
            persistor = DecisionPersistor(session)
            # Bu sembolde HERHANGİ bir bacak (spot ya da perp) zaten
            # açıksa yeni bir çift açma — pairs_trader'ın has_open_
            # position_for_experiment'iyle AYNI kullanım, ama burada
            # ikinci bacağın YANLIŞLIKLA aynı kontrole takılmaması için
            # SADECE çift açmaya BAŞLAMADAN önce, bir kez kontrol edilir.
            if persistor.has_open_position_for_experiment(symbol, EXPERIMENT_BUCKET):
                return None
            open_pair_count = persistor.count_open_positions_for_experiment(EXPERIMENT_BUCKET) // 2
            if open_pair_count >= max_open_pairs:
                return None

        basis_data = fetch_perp_basis(symbol)
        if basis_data is None:
            return None
        if basis_data["basis_pct"] < min_basis_pct or basis_data["funding_rate"] < min_funding_rate:
            return None

        entry_price = basis_data["index_price"]
        if entry_price <= 0:
            return None

        # Faz 344 — kritik bulgu: RiskEngine'in genel aynı-sembol cooldown'u
        # (min_seconds_between_trades, varsayılan 60sn) iki bacağı arka
        # arkaya açmayı GERÇEKTEN engelliyordu (test DEĞİL, canlıda da
        # olurdu — leg 2'nin seconds_since_last_trade'i leg 1 AÇILDIKTAN
        # SONRA taze hesaplanınca ~0 çıkıp cooldown'a takılıyordu). İki
        # bacak, TANIM GEREĞİ tek bir koordineli eylem (eş zamanlı hedge)
        # — risk durumu BİR KEZ, hiçbir bacak açılmadan ÖNCEki dünyayı
        # yansıtacak şekilde okunup ikisine de AYNI anlık görüntü
        # kullandırılıyor. Bu bir güvenlik gevşetmesi değil, doğru atomik-
        # eylem semantiği: karar anında bu sembolde henüz hiçbir işlem
        # olmamıştı, iki bacak da o ana göre değerlendiriliyor.
        risk_state = load_position_risk_state(symbol=symbol)

        spot_opened = self._open_leg(symbol, "LONG", entry_price, leg_capital_usd, basis_data, risk_state)
        if not spot_opened:
            return None
        # Faz 344 — pairs_trader.py ile AYNI, zaten kabul edilmiş
        # sınırlama: ikinci bacak (RiskEngine reddi, kapasite dolması
        # vb. nedenle) açılamazsa, ilk bacak GERİ ALINMAZ — tek-bacaklı
        # (hedge'siz) bir pozisyon kalabilir. Bu, pairs_trader'ın kendi
        # _check_pair'inin de üstlendiği, dokümante edilmiş bir risk.
        perp_opened = self._open_leg(symbol, "SHORT", entry_price, leg_capital_usd, basis_data, risk_state)

        return {
            "symbol": symbol,
            "basis_pct": round(basis_data["basis_pct"], 6),
            "funding_rate": round(basis_data["funding_rate"], 6),
            "opened_legs": ["LONG_spot"] + (["SHORT_perp"] if perp_opened else []),
        }

    def _open_leg(
        self, symbol: str, direction: str, entry_price: float, leg_capital_usd: float,
        basis_data: dict, risk_state: dict,
    ) -> bool:
        ctx = CognitiveCycleContext()
        ctx.market.symbol = symbol
        ctx.market.raw_snapshot = {
            "close": entry_price,
            "basis_arb": symbol,
            "basis_pct": basis_data["basis_pct"],
            "funding_rate": basis_data["funding_rate"],
        }
        ctx.decision.proposed_direction = direction
        ctx.decision.final_size = leg_capital_usd / entry_price
        ctx.decision.filled_price = entry_price
        # Kasıtlı olarak stop_loss_distance/take_profit_distance HİÇ
        # set edilmiyor (bkz. modül üstündeki not) — bu bacak PositionCloser'ın
        # standart stop/hedef taramasından geçmiyor, sadece close_due_
        # basis_arb_pairs() tarafından (çift birlikte) kapatılıyor.

        # Faz 363 — kritik bulgu: LONG (spot) bacağı, decision_recorder'ın
        # sembol-bazlı GENEL kaldıraç ayarını (symbol_leverage) kullanıyordu
        # — cash-and-carry arbitrajın "spot bacak likidasyon riski taşımaz"
        # temel varsayımı ihlal ediliyordu (gerçek olay: SCRTUSDT'de hem
        # LONG hem SHORT bacağı likide oldu, hedge amacın tam tersine
        # döndü). SHORT (perp) bacağı KASITLI OLARAK dokunulmuyor — o zaten
        # kaldıraçlı bir araç (perpetual futures), sembol ayarı geçerli
        # kalmalı.
        if direction == "LONG":
            ctx.decision.leverage_override = 1.0

        ctx.risk.limits = load_active_limits()
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

        ctx = RiskEngine(secret=get_settings().SECRET_KEY).execute(ctx)
        if ctx.risk.evaluation.verdict != "approved":
            return False

        self.recorder.record(ctx, experiment_bucket=EXPERIMENT_BUCKET)
        return True

    def close_due_pairs(self) -> list[dict]:
        """Faz 344 — celery beat tarafından periyodik çağrılır. Bir
        sembolün İKİ bacağı da açıksa VE en eskisi max_hold_hours'ı
        aştıysa, ikisi BİRLİKTE gerçek güncel fiyatla kapatılır — tek
        bacak bağımsız kapanmaz (bkz. modül üstündeki tasarım notu)."""
        with SessionFactory.get_session() as session:
            max_hold_hours = float(AppSettingsRepository(session).get("basis_arbitrage_max_hold_hours"))
            persistor = DecisionPersistor(session)
            open_positions = persistor.list_open_positions_for_experiment(EXPERIMENT_BUCKET)

        by_symbol: dict[str, list[dict]] = {}
        for pos in open_positions:
            by_symbol.setdefault(pos["symbol"], []).append(pos)

        closer = PositionCloser(self.data_provider)
        now = datetime.now(UTC)
        closed = []
        for symbol, legs in by_symbol.items():
            if len(legs) < 2:
                # Hedge'siz kalmış tek bir bacak — v1'de dokunulmuyor
                # (bkz. _try_open_pair'in üstündeki not), ayrı bir
                # operasyonel müdahale konusu.
                continue

            oldest_opened_at = min(leg["opened_at"] for leg in legs)
            age_hours = (now - oldest_opened_at).total_seconds() / 3600
            if age_hours < max_hold_hours:
                continue

            try:
                current_price = self.data_provider.get_ohlcv(symbol, "1m", limit=1)[-1].close
            except Exception:
                continue
            if not current_price or current_price <= 0:
                continue

            with SessionFactory.get_session() as session:
                persistor = DecisionPersistor(session)
                for leg in legs:
                    net_pnl = closer.estimate_net_pnl_if_closed_now(leg, current_price)
                    persistor.close_position(
                        decision_id=str(leg["id"]), exit_price=current_price, pnl=net_pnl,
                        closed_at=now, outcome={"exit_reason": "basis_arb_max_hold"},
                    )
            closed.append({"symbol": symbol, "legs_closed": len(legs), "exit_price": current_price})

        return closed
