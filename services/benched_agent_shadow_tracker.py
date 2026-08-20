"""Shadow Mode: Benched Ajan İtirazı — Faz 268-sonrası'ın (macro_shadow_
tracker.py) doğrudan devamı, kullanıcı isteği: "Benched ajan itirazını
gölge pozisyon testi."

agents/source_reliability_agent.py bir ajanın gerçek son isabet oranı
eşiğin altına düşünce onu "benched" işaretliyor — oy ağırlığı (performance_
weight) sıfırlanıyor, ama opinion listede KALIYOR (services/
council_orchestrator.py'nin "Devre dışı (benched)" caveat'ı, bkz. o
dosyadaki yorum). Bu, gerçek bir soruyu açık bırakıyor: "benching kararı
gerçekten doğru muydu, yoksa iyi bir sinyali mi susturduk?"

macro_shadow_tracker.py ile AYNI izolasyon felsefesi — council'in GERÇEK
kararını hiç etkilemez, `decisions` tablosunu hiç kullanmaz, sanal (paper)
pozisyonlar shadow_positions tablosuna (source alanı zaten serbest metin,
şema değişikliği gerekmiyor) yazılır. macro'dan farkı: TEK bir sabit
kaynak değil, o cycle'da GERÇEKTEN benched olan VE final karardan (WAIT
dahil) FARKLI yön öneren her domain için ayrı bir source ("benched_
<domain>") — böylece "hangi benched ajanın itirazı haklı çıkıyor"
sorusu domain bazında ayrı ayrı cevaplanabilir."""
from datetime import UTC, datetime
from uuid import uuid4

from contracts.shadow_position import ShadowPosition
from database.repositories.shadow_position_repository import ShadowPositionRepository
from database.session_factory import SessionFactory

_BENCHED_CAVEAT_MARKER = "Devre dışı (benched)"


def _is_benched(opinion) -> bool:
    return any(_BENCHED_CAVEAT_MARKER in c for c in (opinion.caveats or []))


def _final_direction(ctx) -> str:
    # DecisionRecorder.record()'un final direction çözümlemesiyle AYNI —
    # tek gerçek kaynak burada da tekrarlanıyor (fusion bu alanları
    # ctx.decision'a zaten yazmış oluyor, propose() bittiğinde).
    decision = getattr(ctx, "decision", None)
    if decision is None:
        return "WAIT"
    return (
        getattr(decision, "proposed_direction", None)
        or getattr(decision, "final_action", None)
        or "WAIT"
    )


def _benched_dissenting_opinions(ctx) -> list[tuple[str, str, float]]:
    """O cycle'da GERÇEKTEN benched olan VE final karardan (WAIT dahil)
    farklı yön öneren her opinion için (domain, direction, confidence).
    Aynı domain'in aynı sembolde tekrar tekrar sanal pozisyon açmasını
    (has_open_position ile) önleyen kontrol çağıran tarafta."""
    final = _final_direction(ctx).upper()
    opinions = ctx.__dict__.get("_last_opinions") or []
    result = []
    for o in opinions:
        if o.direction not in ("LONG", "SHORT"):
            continue
        if o.direction == final:
            continue
        if not _is_benched(o):
            continue
        result.append((o.domain.value, o.direction, o.confidence))
    return result


def process_symbol_opinions(symbol: str, ctx, entry_price: float, data_provider=None) -> None:
    """Ana cycle'ın HER sembol için çağırması gereken tek giriş noktası
    (macro_shadow_tracker.process_symbol_opinion ile AYNI çağrı deseni).
    Kasıtlı olarak fail-closed/sessiz: buradaki HERHANGİ bir hata gerçek
    trading cycle'ını asla etkilememeli."""
    try:
        dissents = _benched_dissenting_opinions(ctx)
        if not dissents:
            return

        from services.macro_shadow_tracker import _atr_based_distance_pct

        # Faz 320 — target_atr_mult artık yöne göre farklı. "not final"
        # tek bir zıt yön bırakır (sadece LONG/SHORT var), bu yüzden
        # dissents içindeki tüm kayıtlar zaten AYNI yöne sahip.
        dissent_direction = dissents[0][1]
        stop_pct, target_pct = _atr_based_distance_pct(symbol, dissent_direction, data_provider)
        if stop_pct is None:
            return

        with SessionFactory.get_session() as session:
            repo = ShadowPositionRepository(session)
            for domain, direction, confidence in dissents:
                source = f"benched_{domain}"
                if repo.has_open_position(source, symbol):
                    continue

                if direction == "LONG":
                    stop_loss_price = entry_price * (1 - stop_pct)
                    take_profit_price = entry_price * (1 + target_pct)
                else:
                    stop_loss_price = entry_price * (1 + stop_pct)
                    take_profit_price = entry_price * (1 - target_pct)

                repo.open_position(ShadowPosition(
                    id=uuid4(),
                    source=source,
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
        structlog.get_logger().warning("benched_agent_shadow_tracker_open_failed", symbol=symbol, exc_info=True)


def list_active_sources() -> list[str]:
    """Şu an açık ya da kapanmış en az bir gölge pozisyonu olan tüm
    "benched_<domain>" kaynaklarını döndürür — dashboard/API'nin hangi
    domain'lerin gerçekten itiraz ettiğini keşfedebilmesi için."""
    from database.repositories.shadow_position_repository import ShadowPositionModel

    with SessionFactory.get_session() as session:
        rows = (
            session.query(ShadowPositionModel.source)
            .filter(ShadowPositionModel.source.like("benched_%"))
            .distinct()
            .all()
        )
    return sorted(r[0] for r in rows)


def close_due_positions() -> list[dict]:
    """close_due_positions_task ile AYNI cadence'te (celery beat) çağrılır
    — macro_shadow_tracker.close_due_positions ile birebir aynı mantık,
    ama TÜM "benched_*" kaynaklarını tarar (kaç farklı domain benched
    olup itiraz ettiyse hepsi)."""
    from market_data.ingestion.data_provider import RoutingProvider

    provider = RoutingProvider()
    closed = []

    with SessionFactory.get_session() as session:
        repo = ShadowPositionRepository(session)
        from database.repositories.shadow_position_repository import ShadowPositionModel
        open_positions = (
            session.query(ShadowPositionModel)
            .filter(ShadowPositionModel.status == "open")
            .filter(ShadowPositionModel.source.like("benched_%"))
            .all()
        )

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
                closed.append({"source": pos.source, "symbol": pos.symbol, "exit_reason": exit_reason, "pnl_pct": pnl_pct})

    return closed
