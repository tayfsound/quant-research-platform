"""Karşı-Olgusal Ajan-Etki Ölçümü — gerçek veriye/canlı pipeline
bileşenlerine dokunan katman (Faz 363). analytics/counterfactual_
trade_replay.py + analytics/agent_ablation.py saf kalıyor.

Kullanıcı sorusu: analytics/agent_ablation.py'nin "flipped_direction"
olarak işaretlediği geçmiş kararlarda (bir ajanın oyu çıkarılınca
council'in nihai yönü DEĞİŞİYOR) — çevirmeseydi ne olurdu, GERÇEKTEN
kâr mı zarar mı olurdu? Gerçekleşen işlemin PNL'ini bu senaryoya
atfetmek yanlış olurdu (TAMAMEN FARKLI bir işlem açılırdı) — bu modül
o karşı-olgusal işlemi risk kapılarından geçirip GERÇEK tarihsel fiyat
verisiyle bar-bar simüle ediyor.

Faz 284'te (2026-08-19) TÜM sembolleri sürekli tarayan, celery'ye bağlı
bir backtest sistemi "karar mekanizmasına hiç katkısı yoktu" gerekçesiyle
TAMAMEN kaldırılmıştı. Bu modül KASITLI olarak farklı: (1) SADECE
geçmişte gerçekleşmiş, sınırlı sayıdaki flip vakasıyla sınırlı, (2)
hiçbir celery task'ına bağlanmıyor — talep üzerine (script/manuel
çağrı) çalışıyor, (3) sonucu gerçek bir soruya (bu ajana güvenilmeli
mi) doğrudan cevap veriyor.

Bilinen, kasıtlı basitleştirmeler (kullanıcı onayıyla, 2026-08-26):
- Pozisyon büyüklüğü: Kelly/CPPI/drawdown-sizing zincirini o tarihsel
  ana göre yeniden kurmak yerine GERÇEKLEŞEN işlemin final_size'ı
  kullanılıyor. Bu, kazanma/kaybetme SINIFLANDIRMASINI ya da yönü hiç
  etkilemiyor — sadece PNL'in dolar büyüklüğünü yaklaşık yapıyor.
- Risk-kapısı girdileri (open_position_count, capital_used_pct,
  consecutive_losses vb.) VE RiskTargetStage'in kalibrasyon/çarpan
  okumaları o tarihsel an yerine ŞU ANKİ (replay çalıştırıldığı andaki)
  durumu kullanıyor — tam point-in-time rekonstrüksiyon bu ölçümün
  kapsamının çok ötesinde bir iş (bkz. plan dosyası). Sonuç her zaman
  data_leakage_caveat=True ile işaretleniyor, "kesin" değil "gerçek
  fiyat verisiyle ama yaklaşık" olarak sunulmalı.

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir ajanın canlı oy hakkını
burada otomatik değiştirmiyor (agent_ablation.py ile AYNI ilke)."""
import asyncio
from datetime import UTC, datetime, timedelta

from analytics.agent_ablation import resynthesize_belief_and_opinions_with_domain_excluded
from analytics.counterfactual_trade_replay import BreakevenSettings, walk_price_path_to_exit
from contracts.context import CognitiveCycleContext
from engines.cognitive_pipeline import RiskGateStage, RiskTargetStage
from engines.risk_engine import RiskEngine
from market_data.ingestion.ohlcv import OHLCV
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_HISTORICAL_BARS = 14 * 24 * 60  # analytics/counterfactual_trade_replay.py::MAX_REPLAY_BARS ile aynı üst sınır


def _market_snapshot_from_contributions(contributions: list[dict]) -> dict | None:
    for item in contributions or []:
        if isinstance(item, dict) and item.get("type") == "market_snapshot":
            return item.get("data") or {}
    return None


def _load_breakeven_settings() -> BreakevenSettings:
    """services/position_closer.py::_load_breakeven_trigger_r_multiple/
    _load_trailing_stop_distance_pct/_load_progressive_lock_* ile AYNI
    anahtarlar/varsayılanlar — replay BAŞINDA bir kez okunur (bar başına
    değil), pure walk_price_path_to_exit'e parametre olarak taşınır."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        trigger = float(repo.get("breakeven_trigger_r_multiple") or 0.5)
        trailing = float(repo.get("trailing_stop_distance_pct") or 0.05)
        lock_min = float(repo.get("progressive_lock_min_profit_r") or 1.0)
        lock_frac = float(repo.get("progressive_lock_fraction") or 0.5)
    return BreakevenSettings(
        trigger_r_multiple=trigger if 0.0 < trigger <= 1.0 else 0.5,
        trailing_pct=trailing if trailing >= 0.0 else 0.05,
        progressive_lock_min_profit_r=lock_min if lock_min > 0.0 else 1.0,
        progressive_lock_fraction=lock_frac if 0.0 < lock_frac <= 1.0 else 0.5,
    )


async def _fetch_historical_bars(symbol: str, since: datetime, max_hold_days: int) -> list[OHLCV]:
    """exchange_gateway/binance/adapter.py::BinanceAdapter.fetch_ohlcv
    zaten `since` (startTime) + 1000-üstü sayfalama destekliyor (Faz 222)
    — yeni bir HTTP çağrısı icat edilmiyor, mevcut, canlıda kullanılan
    aynı istemci. connect()/disconnect() gerekli (client lazy-init)."""
    from exchange_gateway.binance.adapter import BinanceAdapter

    limit = min(max_hold_days * 24 * 60, MAX_HISTORICAL_BARS)
    adapter = BinanceAdapter()
    await adapter.connect()
    try:
        raw_bars = await adapter.fetch_ohlcv(symbol, "1m", since=since, limit=limit)
    finally:
        await adapter.disconnect()
    return [
        OHLCV(
            timestamp=datetime.fromtimestamp(b["time"] / 1000, tz=UTC),
            open=b["open"], high=b["high"], low=b["low"], close=b["close"], volume=b["volume"],
        )
        for b in raw_bars
    ]


def replay_flipped_decision(
    decision_row: dict, excluded_domain: str, breakeven_settings: BreakevenSettings,
    resynth: tuple | None = None,
) -> dict | None:
    """Tek bir gerçek kapanmış karar için: excluded_domain'in oyu
    olmasaydı açılacak KARŞI-OLGUSAL işlemi risk kapılarından geçirip
    (onaylanırsa) GERÇEK tarihsel fiyat verisiyle bar-bar simüle eder.
    Flip yoksa (agent_ablation.py'nin "flipped_direction" DIŞI kategorileri)
    None döner — zorla bir sonuç üretilmez.

    Faz 366-devam — kullanıcı isteği (backlog #51: "onchain'in BTC-özel
    sinyalleri diğer sembollere açılsa ne olurdu"): bu senaryo "bir
    domain'i çıkarma" değil "bir domain'in oyunu DEĞİŞTİRME" — resynth
    verilirse (belief, adjusted_opinions) doğrudan kullanılır, DAHİLİ
    exclude-tabanlı resynthesis atlanır. ~150 satırlık risk/execution
    replay mantığı KOPYALANMADI — tek kaynak burada kalıyor."""
    contributions = decision_row.get("agent_contributions")
    actual_direction = (decision_row.get("direction") or "").upper()
    if not contributions or actual_direction not in ("LONG", "SHORT"):
        return None

    if resynth is None:
        resynth = resynthesize_belief_and_opinions_with_domain_excluded(contributions, excluded_domain)
    if resynth is None:
        return None
    belief, adjusted_opinions = resynth
    if belief.direction in ("WAIT", actual_direction):
        return None  # caused_trade ya da not_pivotal -- replay edilecek FARKLI bir işlem yok
    counterfactual_direction = belief.direction

    market_snapshot = _market_snapshot_from_contributions(contributions)
    entry_price = decision_row.get("entry_price")
    symbol = decision_row.get("symbol")
    opened_at = decision_row.get("opened_at")
    final_size = decision_row.get("quantity")  # bkz. modül üstü not: Kelly/CPPI yerine gerçek boyut
    if not market_snapshot or not entry_price or not symbol or not opened_at or not final_size:
        return {"would_have_traded": False, "rejection_reason": "insufficient_stored_context", "counterfactual_direction": counterfactual_direction}

    ctx = CognitiveCycleContext()
    ctx.market.symbol = symbol
    ctx.market.timeframe = market_snapshot.get("timeframe", "")
    ctx.market.features = market_snapshot.get("features") or {}
    ctx.market.raw_snapshot = market_snapshot.get("raw_snapshot") or {"close": entry_price}
    ctx.decision.proposed_direction = counterfactual_direction
    ctx.decision.final_size = float(final_size)
    ctx.decision.filled_price = entry_price

    # RiskTargetStage: ATR/confluence-tabanlı stop/hedef mesafesi + meta-
    # label boyut çarpanı (engines/cognitive_pipeline.py, gerçek/canlıda
    # kullanılan AYNI aşama — kopyalanmadı, doğrudan çağrıldı).
    ctx = RiskTargetStage().execute(ctx, opinions=adjusted_opinions)
    if not ctx.decision.stop_loss_distance or not ctx.decision.take_profit_distance:
        return {"would_have_traded": False, "rejection_reason": "no_atr_target_available", "counterfactual_direction": counterfactual_direction}

    # Risk-snapshot: bkz. modül üstü not -- o tarihsel an yerine ŞU ANKİ
    # canlı durum (services/risk_state.py::load_position_risk_state,
    # basis_arbitrage_strategy.py::_open_leg ile AYNI alan eşlemesi).
    from database.repositories.risk_limit_repository import load_active_limits
    from services.risk_state import load_position_risk_state

    risk_state = load_position_risk_state(symbol=symbol)
    ctx.risk.limits = load_active_limits()
    ctx.risk.trading_mode = risk_state["trading_mode"]
    ctx.risk.open_position_count = risk_state["open_position_count"]
    ctx.risk.max_concurrent_positions = risk_state["max_concurrent_positions"]
    ctx.risk.capital_used_pct = risk_state["capital_used_pct"]
    ctx.risk.max_capital_pct = risk_state["max_capital_pct"]
    ctx.risk.ai_enabled = risk_state["ai_enabled"]
    ctx.risk.consecutive_losses = risk_state["consecutive_losses"]
    ctx.risk.kill_switch_consecutive_losses = risk_state["kill_switch_consecutive_losses"]
    ctx.risk.concept_drift_reason = risk_state["concept_drift_reason"]

    from config.settings import get_settings

    risk_engine = RiskEngine(secret=get_settings().SECRET_KEY)
    ctx = risk_engine.execute(ctx)
    if ctx.risk.evaluation.verdict != "approved":
        return {
            "would_have_traded": False, "rejection_reason": "risk_engine_rejected",
            "reasons": [r.code for r in ctx.risk.evaluation.reasons], "counterfactual_direction": counterfactual_direction,
        }

    from services.decision_fusion import DecisionFusion

    ctx = DecisionFusion().evaluate(ctx, belief, adjusted_opinions)
    if (ctx.decision.final_size or 0.0) <= 0:
        return {"would_have_traded": False, "rejection_reason": "decision_fusion_ev_gate", "counterfactual_direction": counterfactual_direction}

    ctx = RiskGateStage(risk_engine).execute(ctx)
    if ctx.risk.evaluation.verdict != "approved":
        return {
            "would_have_traded": False, "rejection_reason": "risk_gate_stage_rejected",
            "reasons": [r.code for r in ctx.risk.evaluation.reasons], "counterfactual_direction": counterfactual_direction,
        }

    # Buraya kadar geldiyse: karşı-olgusal işlem GERÇEKTEN açılırdı.
    from simulator.fee_engine import FeeEngine
    from simulator.funding_cost import compute_funding_cost
    from simulator.slippage_model import SlippageModel

    side = "BUY" if counterfactual_direction == "LONG" else "SELL"
    fill_price = SlippageModel().apply(entry_price, side, ctx.decision.final_size)
    entry_notional = fill_price * ctx.decision.final_size
    entry_fee = FeeEngine().calculate(entry_notional, is_maker=False)

    if counterfactual_direction == "LONG":
        stop_price = fill_price - ctx.decision.stop_loss_distance
        target_price = fill_price + ctx.decision.take_profit_distance
    else:
        stop_price = fill_price + ctx.decision.stop_loss_distance
        target_price = fill_price - ctx.decision.take_profit_distance

    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        max_hold_days = int(AppSettingsRepository(session).get("basis_arbitrage_max_hold_hours") or "72") // 24 or 3

    from market_data.ingestion.data_provider import looks_like_binance_pair

    # Faz 363 — kritik bulgu: watchlist sadece kripto DEĞİL (ör. MSFT gibi
    # hisse senetleri de council'e giriyor, bkz. services/tasks.py::
    # ingest_candles_task'ın AYNI filtreyi kullanma nedeni) — BinanceAdapter
    # bu sembolleri hiç bilmiyor. Zorla bir API çağrısı denemek yerine
    # dürüstçe "veri kaynağı yok" döndürülüyor.
    if not looks_like_binance_pair(symbol):
        return {
            "would_have_traded": True, "rejection_reason": None, "exit_reason": None, "pnl": None,
            "no_historical_data": True, "reason": "not_a_binance_symbol", "counterfactual_direction": counterfactual_direction,
        }

    bars = asyncio.run(_fetch_historical_bars(symbol, opened_at, max(max_hold_days, 14)))
    if not bars:
        return {"would_have_traded": True, "rejection_reason": None, "exit_reason": None, "pnl": None, "no_historical_data": True, "counterfactual_direction": counterfactual_direction}

    walk = walk_price_path_to_exit(
        bars, counterfactual_direction, fill_price, stop_price, target_price,
        breakeven_settings, original_stop_price=stop_price,
    )
    if walk["exit_reason"] is None:
        return {"would_have_traded": True, "rejection_reason": None, "exit_reason": None, "pnl": None, "no_exit_within_window": True, "counterfactual_direction": counterfactual_direction}

    exit_price = walk["exit_price"]
    exit_side = "SELL" if counterfactual_direction == "LONG" else "BUY"
    exit_fill_price = SlippageModel().apply(exit_price, exit_side, ctx.decision.final_size)
    exit_notional = exit_fill_price * ctx.decision.final_size
    exit_fee = FeeEngine().calculate(exit_notional, is_maker=False)

    exit_bar = bars[walk["exit_bar_index"]]
    funding_cost = compute_funding_cost(symbol, counterfactual_direction, entry_notional, opened_at, exit_bar.timestamp)

    if counterfactual_direction == "LONG":
        gross_pnl = (exit_fill_price - fill_price) * ctx.decision.final_size
    else:
        gross_pnl = (fill_price - exit_fill_price) * ctx.decision.final_size
    net_pnl = gross_pnl - entry_fee - exit_fee - funding_cost

    return {
        "would_have_traded": True,
        "rejection_reason": None,
        "counterfactual_direction": counterfactual_direction,
        "entry_price": fill_price,
        "exit_price": exit_fill_price,
        "exit_reason": walk["exit_reason"],
        "pnl": round(net_pnl, 6),
        "win": net_pnl > 0,
    }


def gather_counterfactual_agent_impact(agent_domain: str) -> dict:
    """agent_domain'in TÜM "flipped_direction" vakalarını (analytics/
    agent_ablation.py'nin leave-one-out'unun ürettiği) çekip her birini
    replay_flipped_decision ile simüle eder, gerçekleşen SONUÇLA
    karşılaştırır. Talep üzerine çağrılır — hiçbir celery task'ına
    bağlanmıyor (bkz. modül üstü not)."""
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=None, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )

    breakeven_settings = _load_breakeven_settings()
    results = []
    actual_pnls = []
    for t in closed_trades:
        contributions = t.get("agent_contributions")
        actual_direction = t.get("direction")
        pnl = t.get("pnl")
        if not contributions or not actual_direction or pnl is None:
            continue
        resynth = resynthesize_belief_and_opinions_with_domain_excluded(contributions, agent_domain)
        if resynth is None:
            continue
        belief, _ = resynth
        if belief.direction in ("WAIT", actual_direction.upper()):
            continue  # flipped_direction değil -- bu ölçümün kapsamı dışında

        replay = replay_flipped_decision(t, agent_domain, breakeven_settings)
        if replay is None:
            continue
        results.append(replay)
        # Faz 363 — kritik bulgu: Binance hız sınırlayıcısı (dakikada 15
        # istek) TÜM süreçler arasında paylaşılıyor (bkz. project_open_
        # items_2026_08_21.md'deki Faz 347 notu) — canlı trading cycle'ıyla
        # AYNI bütçeyi tüketmemek için her replay'den sonra kısa bir
        # kibarlık gecikmesi.
        import time
        time.sleep(0.3)
        actual_pnls.append(float(pnl))

    traded = [r for r in results if r["would_have_traded"] and r["pnl"] is not None]
    n_wins = sum(1 for r in traded if r["win"])
    counterfactual_total_pnl = sum(r["pnl"] for r in traded)
    actual_total_pnl_same_decisions = sum(actual_pnls)

    verdict = "inconclusive"
    if len(traded) >= 10:
        if counterfactual_total_pnl > actual_total_pnl_same_decisions:
            verdict = "agent_hurt"  # ajanı dahil etmek, dışlamaktan daha kötü sonuç verdi
        elif counterfactual_total_pnl < actual_total_pnl_same_decisions:
            verdict = "agent_helped"
        else:
            verdict = "no_difference"

    return {
        "agent_domain": agent_domain,
        "n_flipped_decisions": len(results),
        "n_would_have_traded": len(traded),
        "n_rejected_or_no_data": len(results) - len(traded),
        "counterfactual_win_rate": round(n_wins / len(traded), 4) if traded else None,
        "counterfactual_total_pnl": round(counterfactual_total_pnl, 4) if traded else None,
        "actual_total_pnl_same_decisions": round(actual_total_pnl_same_decisions, 4),
        "verdict": verdict,
        "data_leakage_caveat": (
            "Risk-kapısı girdileri ve RiskTargetStage'in kalibrasyon/çarpan okumaları bu replay'in "
            "ÇALIŞTIRILDIĞI ANDAKİ canlı duruma göre, pozisyon büyüklüğü gerçekleşen işlemin GERÇEK "
            "boyutuna göre yaklaşık -- tam tarihsel point-in-time doğruluk değil (bkz. modül üstü not)."
        ),
    }
