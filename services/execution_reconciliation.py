"""Faz 315 — Execution Layer, Faz 1: uzlaştırma (reconciliation).

DB'deki execution_mode='testnet' açık pozisyonlarını, borsadaki GERÇEK
durumla periyodik olarak karşılaştırır. close_due_positions_task zaten
her dakika _check_testnet_exit ile aynı kontrolü yapıyor — bu, ikinci,
bağımsız bir güvenlik ağı: o task bir pozisyonu (crash/hata/kısmi
başarısızlık) atlarsa, DB ile borsa sessizce ayrışabilir, kimse fark
etmeyebilir.

Plandaki karar (kullanıcı onaylı): Faz 1 OTOMATİK DÜZELTME YAPMAZ —
sadece işaretler ve loglar, bir insan karar vermeli. Borsa durumundan
sessizce bir DB satırı üretmek/değiştirmek ("asla veri uydurma"
ilkesiyle çelişir) riskli bir varsayım olurdu.
"""
import structlog

from database.repositories.decision_persistor import DecisionPersistor
from database.repositories.event_log_repository import EventLogRepository
from services.execution_service import ExecutionService

logger = structlog.get_logger()

# Borsanın kendi lot-size/step-size yuvarlaması nedeniyle DB'deki
# quantity ile borsadaki positionAmt hiçbir zaman bit-bit eşit olmaz —
# %1'in altındaki farklar mismatch SAYILMIYOR, aksi halde her tur
# gürültüyle dolardı.
_QUANTITY_MISMATCH_TOLERANCE = 0.01


def _detect_mismatch(pos: dict, exchange_position: dict | None) -> str | None:
    if exchange_position is None:
        # close_due_positions_task zaten bunu _check_testnet_exit ile
        # yakalayıp kapatmış olmalı — buraya kadar hâlâ "open" görünüyorsa
        # o task'ın bu pozisyonu atladığının/başarısız olduğunun işareti.
        return "exchange_shows_no_position_but_db_open"

    db_quantity = pos.get("quantity") or 0.0
    exchange_quantity = abs(float(exchange_position.get("positionAmt", 0.0)))
    if db_quantity > 0:
        relative_diff = abs(db_quantity - exchange_quantity) / db_quantity
        if relative_diff > _QUANTITY_MISMATCH_TOLERANCE:
            return "quantity_mismatch"

    exchange_amt = float(exchange_position.get("positionAmt", 0.0))
    exchange_direction = "LONG" if exchange_amt > 0 else "SHORT" if exchange_amt < 0 else None
    db_direction = (pos.get("direction") or "").upper()
    if exchange_direction is not None and db_direction != exchange_direction:
        return "direction_mismatch"

    return None


def reconcile_execution_state(
    decision_repo: DecisionPersistor,
    event_repo: EventLogRepository,
    execution_service: ExecutionService | None = None,
) -> dict:
    execution_service = execution_service or ExecutionService()
    if not execution_service.is_configured():
        return {"skipped": "execution_service_not_configured"}

    positions = decision_repo.list_open_positions(limit=None)
    testnet_positions = [p for p in positions if p.get("execution_mode") == "testnet"]

    mismatches: list[dict] = []
    for pos in testnet_positions:
        symbol = pos["symbol"]
        try:
            exchange_position = execution_service.get_open_position(symbol)
        except Exception as exc:
            logger.warning(
                "execution_reconciliation_check_failed",
                symbol=symbol, decision_id=str(pos["id"]), error=str(exc),
            )
            continue

        reason = _detect_mismatch(pos, exchange_position)
        if reason is None:
            continue

        mismatches.append({"decision_id": str(pos["id"]), "symbol": symbol, "reason": reason})
        decision_repo.update_exchange_sync_status(str(pos["id"]), f"mismatch:{reason}")
        event_repo.record(
            event_type="execution_reconciliation_mismatch",
            entity_type="decision",
            entity_id=pos["id"],
            payload={"symbol": symbol, "reason": reason},
        )
        logger.warning(
            "execution_reconciliation_mismatch",
            symbol=symbol, decision_id=str(pos["id"]), reason=reason,
        )

    return {"checked": len(testnet_positions), "mismatches": len(mismatches), "details": mismatches}
