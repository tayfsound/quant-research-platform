"""Faz 350 — Pozisyon Havuzu / "Max Confidence Modu".

Kullanıcı fikri (2026-08-21): council'dan çıkan yönlü, risk-onaylı bir
karar hemen açılmak yerine bir pencere (varsayılan 15dk) boyunca havuzda
birikir; pencere kapanınca sadece en yüksek confidence'lı top-K aday
GERÇEK, TAZE fiyattan açılır — "her gelene atlamak" yerine "daha garanti
görülene yönelmek".

Varsayılan KAPALI (`max_confidence_mode_enabled=false`) — kapalıyken bu
modül hiç devreye girmez, bugünkü davranış (her risk-onaylı karar hemen
açılır) birebir korunur.

Sadece council'ın normal (deneysel bucket'sız) yolunu etkiler — bkz.
services/decision_recorder.py'deki çağrı noktası. pump_fade/basis_arb/
pairs_trading kendi izole akışlarında DecisionRecorder.record()'u hiç
çağırmıyor, bu yüzden bu havuzdan zaten habersizler."""
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import text

from contracts.decision_event import DecisionEvent
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.repositories.position_pool_repository import (
    PositionPoolCandidateModel,
    PositionPoolRepository,
)
from database.session_factory import SessionFactory

EXPERIMENT_BUCKET = "position_pool_v1"

logger = structlog.get_logger()


def is_enabled() -> bool:
    with SessionFactory.get_session() as session:
        return AppSettingsRepository(session).get("max_confidence_mode_enabled") == "true"


def _resolve_execution_mode(symbol: str) -> str:
    """services/decision_recorder.py::_resolve_execution_mode ile BİREBİR
    AYNI mantık — Faz 370-devam KRİTİK canlı bulgu (kullanıcı: "canlıda
    işlem almamış, test modunda almış sadece"): bu modül GERÇEK Binance
    Testnet/live emri hiç göndermiyordu, execution_mode'u hiç
    okumuyordu — havuzdan açılan HER pozisyon, execution_mode_symbols'ta
    "testnet" olarak işaretlenmiş bir sembol bile olsa, sessizce daima
    simüle ediliyordu. max_confidence_mode_enabled=true olduğu sürece
    (şu an öyle) bu, HAVUZ ÜZERİNDEN açılan TÜM pozisyonların gerçek
    borsaya hiç ulaşmaması demekti."""
    import json

    try:
        with SessionFactory.get_session() as session:
            repo = AppSettingsRepository(session)
            raw_map = repo.get("execution_mode_symbols")
            global_mode = repo.get("execution_mode") or "simulated"
        mapping = json.loads(raw_map) if raw_map else {}
        return mapping.get(symbol, global_mode)
    except Exception:
        return "simulated"


def _symbol_leverage(symbol: str) -> float:
    """services/decision_recorder.py::_symbol_leverage ile AYNI kaynak/
    mantık — havuzlama, council'in NORMAL leverage ayarını kullanır,
    kendi ayrı bir varsayılanı icat etmez."""
    import json

    try:
        with SessionFactory.get_session() as session:
            raw = AppSettingsRepository(session).get("symbol_leverage")
        mapping = json.loads(raw) if raw else {}
        leverage = float(mapping.get(symbol, 1.0))
        return leverage if leverage >= 1.0 else 1.0
    except Exception:
        return 1.0


def try_pool_candidate(
    ctx,
    direction: str,
    entry_price: float | None,
    weight_snapshot_id: UUID | None,
    belief_snapshot_id: UUID | None,
) -> bool:
    """DecisionRecorder.record()'dan çağrılır. Havuzlarsa True döner —
    çağıran taraf bu durumda normal açılışı ATLAMALI (opens_position=False).
    Kapalıysa ya da gerekli veriler eksikse (stop/hedef mesafesi vb.)
    False döner — normal akış hiç etkilenmeden devam eder."""
    if not is_enabled():
        return False

    stop_loss_distance = getattr(ctx.decision, "stop_loss_distance", None)
    take_profit_distance = getattr(ctx.decision, "take_profit_distance", None)
    final_size = getattr(ctx.decision, "final_size", 0.0)

    if not entry_price or stop_loss_distance is None or take_profit_distance is None or final_size <= 0:
        # Gerekli veriler eksikse havuzlamak yerine normal akışa bırak —
        # sessizce yanlış/eksik bir aday kaydetmek yerine fail-open (havuz
        # devre dışıymış gibi davran, mevcut açma mantığı çalışsın).
        return False

    with SessionFactory.get_session() as session:
        settings_repo = AppSettingsRepository(session)
        window_minutes = int(settings_repo.get("max_confidence_mode_pool_window_minutes"))

    now = datetime.now(UTC)
    confidence = getattr(ctx.decision, "confidence", 0.0)
    window_closes_at = now + timedelta(minutes=window_minutes)
    row = PositionPoolCandidateModel(
        symbol=ctx.market.symbol,
        direction=direction,
        confidence=confidence,
        entry_price_at_pool=entry_price,
        stop_loss_distance=stop_loss_distance,
        take_profit_distance=take_profit_distance,
        planned_notional_usd=final_size * entry_price,
        leverage=_symbol_leverage(ctx.market.symbol),
        weight_snapshot_id=weight_snapshot_id,
        belief_snapshot_id=belief_snapshot_id,
        pooled_at=now,
        window_closes_at=window_closes_at,
        status="pending",
    )
    with SessionFactory.get_session() as session:
        PositionPoolRepository(session).add(row)

    logger.info(
        "position_pool_candidate_added",
        symbol=ctx.market.symbol,
        direction=direction,
        confidence=confidence,
        window_closes_at=window_closes_at.isoformat(),
    )
    return True


def _fresh_price(symbol: str) -> float | None:
    try:
        from market_data.ingestion.data_provider import get_ohlcv_provider

        bars = get_ohlcv_provider().get_ohlcv(symbol, "1m", limit=1)
        if not bars:
            return None
        price = bars[-1].close
        return price if price and price > 0 else None
    except Exception:
        return None


def _resolve_leverage(raw_leverage: float, stop_loss_distance: float, fresh_price: float) -> float:
    if raw_leverage <= 1.0:
        return 1.0
    try:
        from simulator.margin import max_safe_leverage

        stop_distance_pct = abs(stop_loss_distance) / fresh_price if fresh_price else None
        if stop_distance_pct is None:
            return raw_leverage
        safe_leverage = max_safe_leverage(stop_distance_pct)
        if safe_leverage is None:
            return raw_leverage
        return max(1.0, min(raw_leverage, safe_leverage))
    except Exception:
        return raw_leverage


def _risk_headroom_ok(symbol: str) -> bool:
    """Pencere kapanana kadar geçen sürede (varsayılan 15dk) sistem
    durumu değişmiş olabilir (limitler dolmuş, AI durdurulmuş vb.) —
    seçilen bir adayı açmadan önce hafif bir "hâlâ mantıklı mı"
    kontrolü. RiskEngine'in TAM tekrarı değil (aday zaten pool anında
    tam risk onayından geçmişti) — sadece en temel, hızlı değişen
    sayaçlar."""
    try:
        from services.risk_state import load_position_risk_state

        state = load_position_risk_state(symbol=symbol)
        if not state["ai_enabled"]:
            return False
        if state["open_position_count"] >= state["max_concurrent_positions"]:
            return False
        if state["capital_used_pct"] >= state["max_capital_pct"]:
            return False
        return True
    except Exception:
        return False


def resolve_due_pool_windows() -> dict:
    """Periyodik Celery görevinden çağrılır (bkz. services/tasks.py::
    resolve_position_pool_task). Penceresi kapanmış TÜM adayları (sembol
    bağımsız, tek havuz) confidence'a göre sırayla top-K'ya keser; geri
    kalanı "rejected" işaretler. Seçilenler TAZE fiyattan (o an gerçek
    piyasa fiyatı — pool anındaki DEĞİL) doğrudan DecisionPersistor ile
    açılır, pump_fade_strategy.py ile AYNI "council pipeline'ını atlayan
    direkt persist" deseni."""
    now = datetime.now(UTC)
    with SessionFactory.get_session() as session:
        settings_repo = AppSettingsRepository(session)
        top_k = int(settings_repo.get("max_confidence_mode_top_k"))
        due_rows = PositionPoolRepository(session).list_due_windows(now)
        # Session'ın `with` bloğu kapanınca ORM nesneleri detach/expire
        # oluyor (attribute erişimi DetachedInstanceError patlatıyor) —
        # ihtiyaç duyulan alanları burada, session hâlâ açıkken düz bir
        # yapıya kopyalıyoruz.
        due = [
            {
                "id": r.id, "symbol": r.symbol, "direction": r.direction,
                "confidence": r.confidence, "stop_loss_distance": r.stop_loss_distance,
                "take_profit_distance": r.take_profit_distance,
                "planned_notional_usd": r.planned_notional_usd, "leverage": r.leverage,
                "weight_snapshot_id": r.weight_snapshot_id, "belief_snapshot_id": r.belief_snapshot_id,
                "pooled_at": r.pooled_at, "window_closes_at": r.window_closes_at,
                "entry_price_at_pool": r.entry_price_at_pool,
            }
            for r in due_rows
        ]

    if not due:
        return {"due": 0, "selected": 0, "rejected": 0, "failed": 0}

    selected_candidates = due[:top_k]
    rejected_candidates = due[top_k:]

    with SessionFactory.get_session() as session:
        repo = PositionPoolRepository(session)
        for c in rejected_candidates:
            repo.mark_resolved(c["id"], "rejected", now)

    opened = 0
    failed = 0
    for c in selected_candidates:
        fresh_price = _fresh_price(c["symbol"])
        if fresh_price is None:
            with SessionFactory.get_session() as session:
                PositionPoolRepository(session).mark_resolved(c["id"], "failed", now)
            failed += 1
            continue

        if not _risk_headroom_ok(c["symbol"]):
            with SessionFactory.get_session() as session:
                PositionPoolRepository(session).mark_resolved(c["id"], "failed", now)
            failed += 1
            continue

        leverage = _resolve_leverage(c["leverage"], c["stop_loss_distance"], fresh_price)
        quantity = c["planned_notional_usd"] / fresh_price
        liquidation_price = None
        if leverage > 1.0:
            from simulator.margin import compute_liquidation_price

            quantity *= leverage
            liquidation_price = compute_liquidation_price(fresh_price, c["direction"], leverage)

        if c["direction"] == "LONG":
            stop_loss_price = fresh_price - c["stop_loss_distance"]
            take_profit_price = fresh_price + c["take_profit_distance"]
        else:
            stop_loss_price = fresh_price + c["stop_loss_distance"]
            take_profit_price = fresh_price - c["take_profit_distance"]

        # Faz 370-devam — KRİTİK canlı bulgu: bu fonksiyon güncellenene
        # kadar HİÇBİR ExecutionService çağrısı yoktu, decision_id'nin
        # oluşturulmasından ÖNCE gerçek emir gönderilemiyordu (event.id
        # client_order_id'ye gömülüyor — bkz. ExecutionService). Şimdi
        # önce id'si sabit bir event nesnesi kuruluyor, GERÇEK emir
        # (varsa) bu id ile gönderiliyor, sonra entry_price/quantity/
        # exchange alanları gerçek dolum sonucuna göre güncelleniyor —
        # services/decision_recorder.py::record() ile AYNI desen.
        execution_mode = _resolve_execution_mode(c["symbol"])
        exchange_order_id = None
        exchange_client_order_id = None
        exchange_stop_order_id = None
        exchange_tp_order_id = None

        # Faz 372 — kullanıcı bulgusu (canlı, gerçek pozisyon üzerinden):
        # "ajan oyları görünmüyor açıklamada" — bu fonksiyon SADECE pool-
        # seçim metadata'sını (pooled_at/entry_price_at_pool vb.) yazıyordu,
        # kararı ÜRETEN gerçek konsey oylarını (macro/technical/pattern/...)
        # hiç taşımıyordu. O oylar KAYBOLMUYOR — ctx.decision.confidence'ı
        # üreten orijinal cycle, try_pool_candidate()'ı çağırmadan hemen
        # önce zaten TAM opinion listesiyle 'no_trade' olarak persist
        # edilmiş oluyor (services/decision_recorder.py, aynı belief_
        # snapshot_id ile) — sadece havuzun AÇTIĞI satırda hiç yoktu.
        # Burada o orijinal satır belief_snapshot_id ile geri bulunup
        # birleştiriliyor; bulunamazsa (fail-open) sadece pool metadata'sı
        # kalır, davranış eskisiyle aynı.
        original_opinions = []
        if c["belief_snapshot_id"] is not None:
            with SessionFactory.get_session() as session:
                original_row = session.execute(
                    text(
                        "SELECT agent_contributions FROM decisions "
                        "WHERE belief_snapshot_id = :bsid AND status = 'no_trade' "
                        "ORDER BY timestamp DESC LIMIT 1"
                    ),
                    {"bsid": str(c["belief_snapshot_id"])},
                ).fetchone()
            if original_row and original_row[0]:
                original_opinions = list(original_row[0])

        event = DecisionEvent(
            timestamp=now,
            symbol=c["symbol"],
            proposed_direction=c["direction"],
            final_action=c["direction"],
            final_size=quantity,
            confidence=c["confidence"],
            agent_opinions=original_opinions + [{
                "type": "position_pool_selection",
                "data": {
                    "pooled_at": c["pooled_at"].isoformat(),
                    "window_closes_at": c["window_closes_at"].isoformat(),
                    "entry_price_at_pool": c["entry_price_at_pool"],
                    "entry_price_at_selection": fresh_price,
                },
            }],
            status="open",
            entry_price=fresh_price,
            quantity=quantity,
            opened_at=now,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            leverage=leverage,
            liquidation_price=liquidation_price,
            weight_snapshot_id=c["weight_snapshot_id"],
            belief_snapshot_id=c["belief_snapshot_id"],
            experiment_bucket=EXPERIMENT_BUCKET,
        )

        if execution_mode == "testnet":
            from services.execution_service import ExecutionService

            execution_service = ExecutionService()
            if execution_service.is_configured():
                exec_result = execution_service.open_position(
                    decision_id=event.id,
                    symbol=c["symbol"],
                    direction=c["direction"],
                    quantity=quantity,
                    stop_loss_price=stop_loss_price,
                    take_profit_price=take_profit_price,
                    leverage=leverage,
                )
                if exec_result is None:
                    # Faz 315'teki AYNI fail-closed ilke: emir teyit
                    # edilemezse asla uydurma bir "open" satırı yazılmaz.
                    with SessionFactory.get_session() as session:
                        PositionPoolRepository(session).mark_resolved(c["id"], "failed", now)
                    logger.warning(
                        "position_pool_testnet_execution_failed",
                        symbol=c["symbol"], candidate_id=str(c["id"]),
                    )
                    failed += 1
                    continue
                event.execution_mode = "testnet"
                event.entry_price = exec_result.entry_price
                event.quantity = exec_result.executed_qty
                event.exchange_order_id = exec_result.exchange_order_id
                event.exchange_client_order_id = exec_result.exchange_client_order_id
                event.exchange_stop_order_id = exec_result.exchange_stop_order_id
                event.exchange_tp_order_id = exec_result.exchange_tp_order_id
            else:
                # resolved_execution_mode "testnet" olsa bile gerçek anahtar
                # yoksa (is_configured() False) fail-closed "simulated" —
                # services/decision_recorder.py ile AYNI davranış.
                event.execution_mode = "simulated"
        else:
            event.execution_mode = "simulated"

        with SessionFactory.get_session() as session:
            DecisionPersistor(session).persist(event)
            PositionPoolRepository(session).mark_resolved(
                c["id"], "selected", now, resulting_decision_id=event.id
            )
        opened += 1

    logger.info(
        "position_pool_window_resolved",
        due=len(due), selected=len(selected_candidates), opened=opened,
        failed=failed, rejected=len(rejected_candidates),
    )
    return {
        "due": len(due), "selected": len(selected_candidates),
        "opened": opened, "failed": failed, "rejected": len(rejected_candidates),
    }
