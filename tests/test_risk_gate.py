"""RiskGateStage integration tests."""
from unittest.mock import MagicMock

from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from engines.cognitive_pipeline import RiskGateStage


class FakeLimit:
    value = 0.5

class FakeEval:
    verdict = ""
    reasons = []

def test_rejects_oversized():
    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.final_size = 1.0
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0

    ctx = stage.execute(ctx)

    assert ctx.decision.action == ActionType.WAIT
    assert ctx.decision.final_size == 0.0
    assert ctx.risk.evaluation.verdict == "rejected"
    assert any(r.code == "POST_FUSION_SIZE_EXCEEDED" for r in ctx.risk.evaluation.reasons)

def test_cheap_asset_with_small_notional_is_not_rejected_for_a_large_unit_count():
    """Faz 370-devam — canlı olay (2026-08-29): ARKMUSDT (~$0.11) için
    final_size=5248.41 BİRİM (~$630 GERÇEK notional) "5248.41 > limit
    5000.0" diye yanlışlıkla reddediliyordu — limit $ notional niyetliydi,
    ham birim sayısıyla kıyaslanıyordu. Aynı $700'lük pozisyon BTC'de
    (~$110k) 0.0064 birime denk geldiği için bu bug hiç görünmüyordu —
    SADECE ucuz varlıklarda (bugün watchlist'e eklenen meme coin'ler)
    ortaya çıktı. current_price verilince artık notional'a göre
    değerlendiriliyor (birim sayısı DEĞİL)."""
    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.final_size = 5248.41167511  # ham birim (ARKM)
    ctx.market.raw_snapshot = {"close": 0.12}  # ~$630 gerçek notional

    class BigLimit:
        value = 5000.0
    ctx.risk.limits = {"max_position_size": BigLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "approved"
    assert ctx.decision.final_size == 5248.41167511


def test_cheap_asset_still_rejected_when_notional_genuinely_exceeds_limit():
    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.final_size = 100000.0  # ham birim
    ctx.market.raw_snapshot = {"close": 0.12}  # notional = 12000 > limit 5000

    class BigLimit:
        value = 5000.0
    ctx.risk.limits = {"max_position_size": BigLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "rejected"
    assert ctx.decision.final_size == 0.0
    assert any(r.code == "POST_FUSION_SIZE_EXCEEDED" for r in ctx.risk.evaluation.reasons)


def test_approves_valid():
    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.final_size = 0.3
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "approved"
    assert ctx.decision.final_size == 0.3


def test_does_not_bypass_checks_in_test_mode():
    """Faz 268-sonrası — kritik bulgu: Faz 262 bu bypass'ı RiskEngine.
    execute() (ön kapı) için kaldırmıştı ("test modu artık live modla
    AYNI kuralları uyguluyor") ama RiskGateStage (son kapı) hâlâ
    trading_mode='test' iken TÜM kontrolleri atlıyordu — gerçek olayda
    (XAUTUSDT SHORT x54) bu son kapı hiç devreye girmemişti."""
    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.risk.trading_mode = "test"
    ctx.decision.final_size = 1.0
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "rejected"
    assert any(r.code == "POST_FUSION_SIZE_EXCEEDED" for r in ctx.risk.evaluation.reasons)


def test_rejects_when_too_many_same_direction_positions_already_open_on_symbol():
    """Faz 268-sonrası — gerçek olay: XAUTUSDT'de aynı yönde (SHORT) 54
    pozisyon aynı anda açık kalabilmişti — max_concurrent_positions
    TOPLAM sayıya bakıyor, bu sembol/yön kombinasyonuna hiç bakmıyordu."""
    from contracts.contexts.decision import ActionType

    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.action = ActionType.ENTER_SHORT
    ctx.decision.final_size = 0.1
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0
    ctx.risk.same_direction_open_counts = {"SHORT": 5, "LONG": 0}
    ctx.risk.max_open_positions_per_symbol_direction = 5

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "rejected"
    assert any(r.code == "MAX_SAME_SYMBOL_DIRECTION_POSITIONS" for r in ctx.risk.evaluation.reasons)


def test_approves_when_same_direction_open_count_is_below_the_limit():
    from contracts.contexts.decision import ActionType

    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.action = ActionType.ENTER_SHORT
    ctx.decision.final_size = 0.1
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0
    ctx.risk.same_direction_open_counts = {"SHORT": 2, "LONG": 0}
    ctx.risk.max_open_positions_per_symbol_direction = 5

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "approved"


def test_same_direction_cap_disabled_when_setting_is_none():
    from contracts.contexts.decision import ActionType

    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.action = ActionType.ENTER_SHORT
    ctx.decision.final_size = 0.1
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0
    ctx.risk.same_direction_open_counts = {"SHORT": 999, "LONG": 0}
    ctx.risk.max_open_positions_per_symbol_direction = None

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "approved"


def test_rejects_reduce_action_when_too_many_same_direction_positions_open():
    """Faz 405 — kritik bulgu, kullanıcı gözlemi (2026-09-01): bu kapı
    SADECE ENTER_LONG/ENTER_SHORT'u görüyordu, Faz 388'in test-modu (VE
    canlı moddaki normal) REDUCE aksiyonunu (final_size = proposed_size *
    confidence, GERÇEK yeni bir pozisyon açıyor) TAMAMEN atlıyordu.
    Gerçek olay: BRKBUSDT'de limit 20 iken 23 LONG pozisyon aynı anda
    açık kalmıştı, hepsi REDUCE üzerinden."""
    from contracts.contexts.decision import ActionType

    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.action = ActionType.REDUCE
    ctx.decision.proposed_direction = "LONG"
    ctx.decision.final_size = 0.1
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0
    ctx.risk.same_direction_open_counts = {"LONG": 23, "SHORT": 4}
    ctx.risk.max_open_positions_per_symbol_direction = 20

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "rejected"
    assert any(r.code == "MAX_SAME_SYMBOL_DIRECTION_POSITIONS" for r in ctx.risk.evaluation.reasons)
    assert ctx.decision.action == ActionType.WAIT
    assert ctx.decision.final_size == 0.0


def test_approves_reduce_action_when_same_direction_open_count_is_below_the_limit():
    from contracts.contexts.decision import ActionType

    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.action = ActionType.REDUCE
    ctx.decision.proposed_direction = "LONG"
    ctx.decision.final_size = 0.1
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0
    ctx.risk.same_direction_open_counts = {"LONG": 3, "SHORT": 0}
    ctx.risk.max_open_positions_per_symbol_direction = 20

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "approved"


def test_reduce_action_with_no_proposed_direction_is_not_gated_fail_closed():
    """proposed_direction hiç yoksa/WAIT ise (icat edilmiş bir yön asla
    varsayılmaz) bu kapı devreye girmemeli — başka bir gate'in işi."""
    from contracts.contexts.decision import ActionType

    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.action = ActionType.REDUCE
    ctx.decision.proposed_direction = None
    ctx.decision.final_size = 0.1
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0
    ctx.risk.same_direction_open_counts = {"LONG": 999, "SHORT": 0}
    ctx.risk.max_open_positions_per_symbol_direction = 20

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "approved"


def test_wait_action_is_never_gated_by_the_same_symbol_direction_cap():
    from contracts.contexts.decision import ActionType

    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.action = ActionType.WAIT
    ctx.decision.proposed_direction = "LONG"
    ctx.decision.final_size = 0.0
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0
    ctx.risk.same_direction_open_counts = {"LONG": 999, "SHORT": 0}
    ctx.risk.max_open_positions_per_symbol_direction = 20

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "approved"


def test_rejects_when_same_symbol_direction_notional_exceeds_capital_cap():
    """Faz 358 — kullanıcı bulgusu: gerçek olay XAUTUSDT LONG'da 17
    pozisyon, hepsi %0.15'lik bir fiyat bandında — sayı-bazlı gate
    (kullanıcı isteğiyle 1000'e gevşetildiği için) bunu yakalamadı. Bu,
    AYRI bir $-bazlı tavan: aynı sembol/yönde bağlı GERÇEK marjin
    starting_capital'ın bir fraksiyonunu geçerse reddedilmeli."""
    from contracts.contexts.decision import ActionType

    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.action = ActionType.ENTER_LONG
    ctx.decision.final_size = 0.1
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0
    ctx.risk.starting_capital = 1_000_000.0
    ctx.risk.same_direction_open_notional = {"LONG": 200_000.0, "SHORT": 0.0}
    ctx.risk.max_same_symbol_direction_capital_pct = 0.15  # cap = $150k, mevcut $200k zaten üzerinde

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "rejected"
    assert any(r.code == "MAX_SAME_SYMBOL_DIRECTION_CAPITAL" for r in ctx.risk.evaluation.reasons)


def test_approves_when_same_symbol_direction_notional_is_below_capital_cap():
    from contracts.contexts.decision import ActionType

    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.action = ActionType.ENTER_LONG
    ctx.decision.final_size = 0.1
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0
    ctx.risk.starting_capital = 1_000_000.0
    ctx.risk.same_direction_open_notional = {"LONG": 50_000.0, "SHORT": 0.0}
    ctx.risk.max_same_symbol_direction_capital_pct = 0.15  # cap = $150k, mevcut $50k altinda

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "approved"


def test_same_symbol_direction_capital_cap_disabled_when_setting_is_none():
    from contracts.contexts.decision import ActionType

    stage = RiskGateStage(MagicMock())
    ctx = CognitiveCycleContext()
    ctx.decision.action = ActionType.ENTER_LONG
    ctx.decision.final_size = 0.1
    ctx.risk.limits = {"max_position_size": FakeLimit()}
    ctx.risk.evaluation = FakeEval()
    ctx.risk.current_drawdown = 0.0
    ctx.risk.starting_capital = 1_000_000.0
    ctx.risk.same_direction_open_notional = {"LONG": 999_999_999.0, "SHORT": 0.0}
    ctx.risk.max_same_symbol_direction_capital_pct = None

    ctx = stage.execute(ctx)

    assert ctx.risk.evaluation.verdict == "approved"
