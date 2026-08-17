"""Shadow Mode: Macro-Only karşılaştırma — Faz 268-sonrası.

Kullanıcı bulgusu: 23 pozisyonluk gerçek örneklemde macro ajanının yönlü
tahminleri ~%86 isabetli görünüyordu — diğer 8 ajanın gürültü ekleyip
eklemediği sorusu doğdu. Ama survivorship bias (macro sadece EMİN olduğu
anlarda yönlü konuşuyor olabilir) ve zaman çerçevesi çatışması (technical
kısa vadeli düzeltmeyi doğru görüp macro orta vadeli trendi tutturmuş
olabilir) riskleri var — küçük örneklemden mimari karar almak (council'i
küçültmek) tam da bu riskleri mimariye gömer.

Kullanıcıyla üzerinde anlaşılan çerçeve (3 seçenekten A): council'in
GERÇEK kararlarını hiç etkilemeyen, SADECE macro'nun kendi yönüne göre
sanal (paper) pozisyon açıp kapatan izole bir gölge takipçi. pump_fade_
strategy.py ile AYNI izolasyon felsefesi — ama pump_fade'den farklı
olarak `decisions` tablosunu HİÇ kullanmıyor (bkz. contracts/
shadow_position.py docstring'i: shadow pozisyonlar gerçek sermaye değil,
dashboard PnL/ROI'ye asla karışmamalı).

Veri kaynağı: gerçek trading cycle'ının (services/orchestrator.py::
run_portfolio_aware_cycle) HER sembol için zaten hesapladığı council
opinion'ları (CognitiveEngine.run() ctx.__dict__["_last_opinions"]'a
yazıyor, persist=False olsa bile) — macro'nun o cycle'da GERÇEKTEN ne
dediğini ayrı bir CognitiveEngine geçişi çalıştırmadan, ek maliyetsiz
okuyoruz. process_symbol_opinion() bu yüzden ctx üretiminden SONRA,
mevcut cycle'ın içinden çağrılır (bkz. çağrı noktası: orchestrator.py)."""
from datetime import UTC, datetime
from uuid import uuid4

from contracts.agent import AgentDomain
from contracts.shadow_position import ShadowPosition
from database.repositories.shadow_position_repository import ShadowPositionRepository
from database.session_factory import SessionFactory

SOURCE = "macro"


def _macro_opinion(ctx) -> tuple[str, float] | None:
    opinions = ctx.__dict__.get("_last_opinions") or []
    for o in opinions:
        if o.domain == AgentDomain.MACRO:
            if o.direction in ("LONG", "SHORT"):
                return o.direction, o.confidence
            return None
    return None


def process_symbol_opinion(symbol: str, ctx, entry_price: float, data_provider=None) -> None:
    """Ana cycle'ın HER sembol için çağırması gereken tek giriş noktası.
    Kasıtlı olarak fail-closed/sessiz: gölge takipçideki HERHANGİ bir
    hata gerçek trading cycle'ını asla etkilememeli — bu yüzden hata
    yutuluyor (yalnızca log).

    data_provider: orchestrator'ın KENDİ (test'lerde mock'lanabilen)
    provider'ı geçilir — burada kendi RoutingProvider'ını kurmak, gerçek
    cycle'ı tamamen mock veri kullanan testlerde bile sessizce gerçek
    ağ çağrısına düşürürdü (bkz. bu fonksiyonun test dosyasındaki not)."""
    try:
        macro = _macro_opinion(ctx)
        if macro is None:
            return
        direction, confidence = macro

        with SessionFactory.get_session() as session:
            repo = ShadowPositionRepository(session)
            if repo.has_open_position(SOURCE, symbol):
                return

            stop_pct, target_pct = _atr_based_distance_pct(symbol, data_provider)
            if stop_pct is None:
                return

            if direction == "LONG":
                stop_loss_price = entry_price * (1 - stop_pct)
                take_profit_price = entry_price * (1 + target_pct)
            else:
                stop_loss_price = entry_price * (1 + stop_pct)
                take_profit_price = entry_price * (1 - target_pct)

            repo.open_position(ShadowPosition(
                id=uuid4(),
                source=SOURCE,
                symbol=symbol,
                direction=direction,
                confidence=confidence,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                opened_at=datetime.now(UTC),
            ))
    except Exception:
        import structlog
        structlog.get_logger().warning("macro_shadow_tracker_open_failed", symbol=symbol, exc_info=True)


def _atr_based_distance_pct(symbol: str, data_provider=None) -> tuple[float | None, float | None]:
    """Gerçek sistemin RiskTargetStage'inin kullandığı AYNI günlük
    ATR-tabanlı formül (bkz. engines/cognitive_pipeline.py::
    RiskTargetStage) — adil bir karşılaştırma için macro'nun gölge
    pozisyonu da council'in kullandığı AYNI risk ölçeğiyle açılıyor."""
    from engines.cognitive_pipeline import RiskTargetStage
    from market_data.features.signal_engine import compute_daily_atr_pct
    from market_data.ingestion.data_provider import RoutingProvider

    provider = data_provider or RoutingProvider()
    daily_bars = provider.get_ohlcv(symbol, "1d", limit=30)
    daily_atr_pct = compute_daily_atr_pct(daily_bars) if daily_bars else None
    if daily_atr_pct is None:
        return None, None

    stop_mult, target_mult, min_stop_pct = RiskTargetStage()._load_multipliers()
    stop_pct = stop_mult * daily_atr_pct
    target_pct = target_mult * daily_atr_pct
    if stop_pct < min_stop_pct:
        scale = min_stop_pct / stop_pct
        stop_pct *= scale
        target_pct *= scale
    return stop_pct, target_pct


def close_due_positions() -> list[dict]:
    """close_due_positions_task ile AYNI cadence'te (celery beat) çağrılır.
    Gerçek pozisyonlardan farklı olarak likidasyon/kısmi kapama yok —
    sadece stop/hedef vuruşu, PositionCloser'ın en basit hâli."""
    from market_data.ingestion.data_provider import RoutingProvider

    provider = RoutingProvider()
    closed = []

    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        open_positions = repo.list_open(source=SOURCE)

        for pos in open_positions:
            try:
                data = provider.get_ohlcv(pos.symbol, "1m", limit=1)
            except Exception:
                continue
            if not data:
                continue
            price = data[-1].close

            exit_reason = None
            if pos.direction == "LONG":
                if price <= pos.stop_loss_price:
                    exit_reason = "stop_loss"
                elif price >= pos.take_profit_price:
                    exit_reason = "take_profit"
            else:
                if price >= pos.stop_loss_price:
                    exit_reason = "stop_loss"
                elif price <= pos.take_profit_price:
                    exit_reason = "take_profit"

            if exit_reason:
                pnl_pct = repo.close_position(pos.id, price, exit_reason, datetime.now(UTC))
                closed.append({"symbol": pos.symbol, "exit_reason": exit_reason, "pnl_pct": pnl_pct})

    return closed
