"""Faz 315 — Execution Layer, Faz 1: uzlaştırma. Sahte repo/execution
service ile — hiç gerçek DB/ağ, sadece services/execution_reconciliation.py'nin
KENDİ karşılaştırma mantığını izole test eder."""
import uuid

from services.execution_reconciliation import _detect_mismatch, reconcile_execution_state


class _FakeDecisionRepo:
    def __init__(self, positions):
        self._positions = positions
        self.sync_status_updates: list[tuple[str, str]] = []

    def list_open_positions(self, limit=None, offset=0):
        return self._positions

    def update_exchange_sync_status(self, decision_id: str, status: str) -> None:
        self.sync_status_updates.append((decision_id, status))


class _FakeEventRepo:
    def __init__(self):
        self.recorded: list[dict] = []

    def record(self, event_type, entity_type=None, entity_id=None, payload=None):
        self.recorded.append({
            "event_type": event_type, "entity_type": entity_type,
            "entity_id": entity_id, "payload": payload,
        })


class _FakeExecutionService:
    def __init__(self, configured: bool, positions_by_symbol: dict):
        self._configured = configured
        self._positions_by_symbol = positions_by_symbol

    def is_configured(self) -> bool:
        return self._configured

    def get_open_position(self, symbol: str):
        return self._positions_by_symbol.get(symbol)


def _testnet_pos(decision_id, symbol, direction="LONG", quantity=0.5):
    return {"id": decision_id, "symbol": symbol, "direction": direction, "quantity": quantity, "execution_mode": "testnet"}


def test_reconcile_skips_entirely_when_execution_service_not_configured():
    service = _FakeExecutionService(configured=False, positions_by_symbol={})
    result = reconcile_execution_state(_FakeDecisionRepo([]), _FakeEventRepo(), execution_service=service)
    assert result == {"skipped": "execution_service_not_configured"}


def test_reconcile_ignores_simulated_positions():
    positions = [{"id": uuid.uuid4(), "symbol": "BTCUSDT", "direction": "LONG", "quantity": 0.5, "execution_mode": "simulated"}]
    service = _FakeExecutionService(configured=True, positions_by_symbol={})
    result = reconcile_execution_state(_FakeDecisionRepo(positions), _FakeEventRepo(), execution_service=service)
    assert result["checked"] == 0
    assert result["mismatches"] == 0


def test_reconcile_flags_position_open_in_db_but_missing_on_exchange():
    decision_id = uuid.uuid4()
    positions = [_testnet_pos(decision_id, "BTCUSDT")]
    decision_repo = _FakeDecisionRepo(positions)
    event_repo = _FakeEventRepo()
    service = _FakeExecutionService(configured=True, positions_by_symbol={})

    result = reconcile_execution_state(decision_repo, event_repo, execution_service=service)

    assert result["checked"] == 1
    assert result["mismatches"] == 1
    assert result["details"][0]["reason"] == "exchange_shows_no_position_but_db_open"
    assert decision_repo.sync_status_updates == [(str(decision_id), "mismatch:exchange_shows_no_position_but_db_open")]
    assert event_repo.recorded[0]["event_type"] == "execution_reconciliation_mismatch"


def test_reconcile_does_not_flag_when_db_and_exchange_agree():
    decision_id = uuid.uuid4()
    positions = [_testnet_pos(decision_id, "BTCUSDT", direction="LONG", quantity=0.5)]
    service = _FakeExecutionService(configured=True, positions_by_symbol={"BTCUSDT": {"positionAmt": "0.5"}})

    result = reconcile_execution_state(_FakeDecisionRepo(positions), _FakeEventRepo(), execution_service=service)

    assert result["checked"] == 1
    assert result["mismatches"] == 0


def test_detect_mismatch_none_when_exchange_missing():
    assert _detect_mismatch({"quantity": 0.5, "direction": "LONG"}, None) == "exchange_shows_no_position_but_db_open"


def test_detect_mismatch_quantity_beyond_tolerance():
    pos = {"quantity": 1.0, "direction": "LONG"}
    assert _detect_mismatch(pos, {"positionAmt": "0.5"}) == "quantity_mismatch"


def test_detect_mismatch_quantity_within_tolerance_is_not_flagged():
    # Binance'in step-size yuvarlaması: %1'in altındaki fark gürültü sayılır.
    pos = {"quantity": 1.0, "direction": "LONG"}
    assert _detect_mismatch(pos, {"positionAmt": "0.995"}) is None


def test_detect_mismatch_direction_mismatch():
    pos = {"quantity": 0.5, "direction": "LONG"}
    # positionAmt negatif == borsada aslında SHORT.
    assert _detect_mismatch(pos, {"positionAmt": "-0.5"}) == "direction_mismatch"


def test_detect_mismatch_none_when_everything_agrees():
    pos = {"quantity": 0.5, "direction": "SHORT"}
    assert _detect_mismatch(pos, {"positionAmt": "-0.5"}) is None
