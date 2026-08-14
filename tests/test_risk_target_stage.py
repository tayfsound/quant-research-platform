"""Faz 191: kritik bulgu — DecisionFusion, ctx.decision.take_profit/stop_loss'a
bakıp Expected Value hesaplıyordu ama hiçbir kod bu ikisini hiçbir zaman set
etmiyordu (hep None -> win=0, loss=0, ev her zaman <=0). Bu, Council ne
önerirse önersin HER işlemi WAIT'e zorluyordu — sistemin bu oturumda inşa
edilen tüm gerçek pozisyon yaşam döngüsü (Faz 187-190) hiçbir zaman gerçek
bir pozisyon açamıyordu. RiskTargetStage bunu gerçek ATR'den (signal_engine.py)
standart bir risk/ödül hedefiyle kapatıyor.

Faz 251: kritik bulgu — sinyal zaman diliminin (candle_timeframe, genelde
1m) ATR'si kripto gibi yüksek volatiliteli bir piyasada bile gürültü
seviyesinde kalıyordu (gerçek ölçüm: BTCUSDT 1m ATR fiyatın ~%0.05'i) —
stop, bir mumun sıradan dalgalanmasından bile küçük kalıp anında
tetikleniyordu (kullanıcı bulgusu: $1900'lük pozisyonlarda $0.07 stop
gibi anlamsız değerler). Artık günlük ATR YÜZDESİ (sinyal zaman
diliminden bağımsız) + güncel fiyattan türetiliyor, 2.5x/5x çarpanla."""
from engines.cognitive_pipeline import RiskTargetStage
from services.decision_fusion import DecisionFusion
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from contracts.belief import Belief


def _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0, confidence=0.6):
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "BTCUSDT"
    ctx.market.features = {"daily_atr_pct": daily_atr_pct}
    ctx.market.raw_snapshot = {"close": current_price}
    ctx.decision.proposed_direction = direction
    ctx.decision.proposed_size = 0.3
    ctx.decision.final_size = 0.3
    ctx.decision.confidence = confidence
    # MetaStage, DecisionFusion çalışmadan ÖNCE action'ı ENTER_LONG/SHORT'a
    # set eder (bkz. engines/cognitive_pipeline.py:MetaStage) — burada onu
    # elle taklit ediyoruz. DecisionFusion sadece REDDEDERKEN action'ı
    # WAIT'e zorluyor, onayladığında dokunmuyor.
    if direction == "LONG":
        ctx.decision.action = ActionType.ENTER_LONG
    elif direction == "SHORT":
        ctx.decision.action = ActionType.ENTER_SHORT
    return ctx


def _belief(direction="LONG", strength=0.6):
    return Belief(direction=direction, strength=strength)


def test_risk_target_stage_sets_take_profit_and_stop_loss_from_daily_atr_pct():
    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
    ctx = RiskTargetStage().execute(ctx)

    assert abs(ctx.decision.stop_loss - 5.0) < 1e-9  # 100 * 2.5 * 0.02
    # Faz 268-sonrası: gerçek OOS doğrulaması 1:4'ün (2.5x/10.0x) tersini
    # işaret etti — hedef, stop'tan KÜÇÜK olmalı (bkz. app_settings_
    # repository.py::DEFAULTS["target_atr_mult"] üstündeki not).
    # Varsayılan artık 1.4x — 100 * 1.4 * 0.02 = 2.8.
    assert abs(ctx.decision.take_profit - 2.8) < 1e-9


def test_risk_target_stage_widens_stop_to_the_min_floor_preserving_the_ratio():
    """Faz 268-sonrası — gerçek bulgu: trade_type'a göre ayrılmış kapanmış
    işlemlerde "scalp" (stop < %4.5) tek başına toplam zararın %92'siydi.
    Düşük daily_atr_pct'te ham stop %4.5 tabanının altına düşerse, SL/TP
    ORANI KORUNARAK genişletilmeli — asla daraltılmamalı."""
    ctx = _ctx(direction="LONG", daily_atr_pct=0.01, current_price=100.0)
    ctx = RiskTargetStage().execute(ctx)

    # Ham: stop=2.5*0.01=%2.5 (taban %4.5'in altında) -> 1.8x ölçeklenir.
    assert abs(ctx.decision.stop_loss - 4.5) < 1e-9  # 100 * %4.5 taban
    assert abs(ctx.decision.take_profit - 2.52) < 1e-9  # 100 * 1.4*0.01*1.8
    # Oran korunmalı: taban öncesi (1.4/2.5) ile taban sonrası aynı.
    ratio_before = (1.4 * 0.01) / (2.5 * 0.01)
    ratio_after = ctx.decision.take_profit / ctx.decision.stop_loss
    assert abs(ratio_before - ratio_after) < 1e-9


def test_risk_target_stage_leaves_targets_unset_for_wait():
    ctx = _ctx(direction="WAIT", daily_atr_pct=0.02)
    ctx = RiskTargetStage().execute(ctx)

    assert ctx.decision.stop_loss is None
    assert ctx.decision.take_profit is None


def test_risk_target_stage_leaves_targets_unset_when_no_daily_atr():
    """Günlük ATR yoksa (yetersiz veri) hedef icat edilmiyor —
    DecisionFusion dürüstçe reddetmeye devam ediyor, sahte bir sayı
    üretilmiyor."""
    ctx = _ctx(direction="LONG", daily_atr_pct=0.0)
    ctx = RiskTargetStage().execute(ctx)

    assert ctx.decision.stop_loss is None
    assert ctx.decision.take_profit is None


def test_decision_fusion_no_longer_forces_wait_once_real_targets_are_set():
    """Bu, gerçek bulgunun kanıtı: RiskTargetStage olmadan (take_profit/
    stop_loss None) DecisionFusion HER ZAMAN ev<=0 -> WAIT üretiyordu.
    RiskTargetStage'in günlük ATR'den kurduğu hedefle, makul bir
    confidence'ta artık pozitif EV ile onaylanabiliyor.

    Faz 268-sonrası: yeni varsayılan oran (1:0.56) breakeven için daha
    yüksek bir kazanma olasılığı gerektiriyor (~%64, eski 1:4 oranın
    %20'sinin tersine) — bu test artık daha yüksek bir confidence/
    strength kullanıyor, hâlâ pozitif EV'nin gerçekten üretildiğini
    kanıtlamak için."""
    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0, confidence=0.85)
    ctx = RiskTargetStage().execute(ctx)

    ctx = DecisionFusion().evaluate(ctx, _belief(direction="LONG", strength=0.85))

    assert ctx.decision.action.value != "WAIT"
    assert ctx.decision.final_size > 0


def test_multipliers_are_read_from_app_settings_not_hardcoded():
    """Faz 268-sonrası — kritik bulgu: STOP_ATR_MULT/TARGET_ATR_MULT eskiden
    sınıf sabitiydi, DSR henüz kanıtlanmamışken bu oranı hızla ayarlamak
    redeploy gerektiriyordu. Artık AppSettings'ten okunuyor."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("target_atr_mult", "3.0", updated_by="test")
    try:
        ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
        ctx = RiskTargetStage().execute(ctx)
        assert abs(ctx.decision.take_profit - 6.0) < 1e-9  # 100 * 3.0 * 0.02
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("target_atr_mult", "1.4", updated_by="test")


def _set_adaptive_barrier_enabled(value: str) -> None:
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("adaptive_barrier_enabled", value, updated_by="test")


def test_risk_target_stage_uses_adaptive_barrier_when_enabled_and_bucket_matches(monkeypatch):
    """Faz 268-sonrası — kullanıcı isteği: Adaptive Barrier Engine wire
    edildi. Gerçek bir kova varsa VE açıksa, statik ATR hesabı YERİNE
    o kovanın sl_pct/tp_pct'i kullanılmalı."""
    from analytics.barrier_table_repository import BarrierTableRepository

    # sl_pct=%6 kasıtlı olarak DEFAULT_MIN_STOP_PCT (%4.5) tabanının
    # ÜSTÜNDE — taban genişletmesiyle karışmasın, sadece "adaptive yol
    # gerçekten kullanılıyor mu" izole test ediliyor (taban ayrı bir
    # testte, aşağıda).
    stored = {
        "sample_count": 250,
        "group_by": ["direction", "regime", "volatility_regime"],
        "table": {"direction=LONG|regime=bull_trend|volatility_regime=normal": {"sl_pct": 0.06, "tp_pct": 0.05}},
    }
    monkeypatch.setattr(BarrierTableRepository, "get_latest", lambda self: stored)
    _set_adaptive_barrier_enabled("true")
    try:
        ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
        ctx.market.features = {
            "daily_atr_pct": 0.02, "long_term_trend_regime": "bull_trend", "volatility_regime": "normal",
        }
        ctx = RiskTargetStage().execute(ctx)
        assert abs(ctx.decision.stop_loss - 6.0) < 1e-9   # 100 * 0.06 (adaptive, statik 2.5*0.02=5.0 DEĞİL)
        assert abs(ctx.decision.take_profit - 5.0) < 1e-9  # 100 * 0.05
    finally:
        _set_adaptive_barrier_enabled("true")


def test_risk_target_stage_falls_back_to_static_atr_when_adaptive_barrier_disabled(monkeypatch):
    from analytics.barrier_table_repository import BarrierTableRepository

    stored = {
        "sample_count": 250,
        "group_by": ["direction", "regime", "volatility_regime"],
        "table": {"direction=LONG|regime=bull_trend|volatility_regime=normal": {"sl_pct": 0.03, "tp_pct": 0.05}},
    }
    monkeypatch.setattr(BarrierTableRepository, "get_latest", lambda self: stored)
    _set_adaptive_barrier_enabled("false")
    try:
        ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
        ctx.market.features = {
            "daily_atr_pct": 0.02, "long_term_trend_regime": "bull_trend", "volatility_regime": "normal",
        }
        ctx = RiskTargetStage().execute(ctx)
        assert abs(ctx.decision.stop_loss - 5.0) < 1e-9  # statik: 100 * 2.5 * 0.02
    finally:
        _set_adaptive_barrier_enabled("true")


def test_risk_target_stage_falls_back_when_no_matching_bucket(monkeypatch):
    """Tablo var ve açık ama bu kararın kovası (yön/rejim/volatilite)
    tabloda yoksa (fail-closed) statik ATR hesabına düşülmeli."""
    from analytics.barrier_table_repository import BarrierTableRepository

    stored = {
        "sample_count": 250,
        "group_by": ["direction", "regime", "volatility_regime"],
        "table": {"direction=SHORT|regime=bear_trend|volatility_regime=high": {"sl_pct": 0.03, "tp_pct": 0.05}},
    }
    monkeypatch.setattr(BarrierTableRepository, "get_latest", lambda self: stored)
    _set_adaptive_barrier_enabled("true")
    try:
        ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
        ctx.market.features = {
            "daily_atr_pct": 0.02, "long_term_trend_regime": "bull_trend", "volatility_regime": "normal",
        }
        ctx = RiskTargetStage().execute(ctx)
        assert abs(ctx.decision.stop_loss - 5.0) < 1e-9  # statik: 100 * 2.5 * 0.02
    finally:
        _set_adaptive_barrier_enabled("true")


def test_risk_target_stage_falls_back_when_no_table_saved_yet(monkeypatch):
    from analytics.barrier_table_repository import BarrierTableRepository

    monkeypatch.setattr(BarrierTableRepository, "get_latest", lambda self: None)
    _set_adaptive_barrier_enabled("true")
    try:
        ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
        ctx = RiskTargetStage().execute(ctx)
        assert abs(ctx.decision.stop_loss - 5.0) < 1e-9  # statik: 100 * 2.5 * 0.02
    finally:
        _set_adaptive_barrier_enabled("true")


def test_adaptive_barrier_still_respects_the_min_stop_pct_floor(monkeypatch):
    """Adaptive öneri de min_stop_pct tabanından ASLA muaf değil — aynı
    güvenlik tabanı her iki yoldan da geçerli."""
    from analytics.barrier_table_repository import BarrierTableRepository

    stored = {
        "sample_count": 250,
        "group_by": ["direction", "regime", "volatility_regime"],
        # sl_pct=%1 -> DEFAULT_MIN_STOP_PCT (%4.5) tabanının altında.
        "table": {"direction=LONG|regime=bull_trend|volatility_regime=normal": {"sl_pct": 0.01, "tp_pct": 0.02}},
    }
    monkeypatch.setattr(BarrierTableRepository, "get_latest", lambda self: stored)
    _set_adaptive_barrier_enabled("true")
    try:
        ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
        ctx.market.features = {
            "daily_atr_pct": 0.02, "long_term_trend_regime": "bull_trend", "volatility_regime": "normal",
        }
        ctx = RiskTargetStage().execute(ctx)
        assert abs(ctx.decision.stop_loss - 4.5) < 1e-9  # taban uygulanmış: 100 * %4.5
        # Oran korunmuş olmalı: taban öncesi (0.02/0.01) ile sonrası aynı.
        ratio_before = 0.02 / 0.01
        ratio_after = ctx.decision.take_profit / ctx.decision.stop_loss
        assert abs(ratio_before - ratio_after) < 1e-9
    finally:
        _set_adaptive_barrier_enabled("true")


def test_decision_fusion_still_forces_wait_without_risk_target_stage():
    """Regresyon kilidi: RiskTargetStage atlanırsa (eski, bug'lı davranış)
    DecisionFusion hâlâ her zaman WAIT'e zorlamalı — bu testin kendisi
    orijinal bug'ı belgeliyor."""
    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, confidence=0.9)
    # RiskTargetStage.execute() KASITLI OLARAK çağrılmıyor.

    ctx = DecisionFusion().evaluate(ctx, _belief(direction="LONG", strength=0.9))

    assert ctx.decision.action.value == "WAIT"
    assert ctx.decision.final_size == 0.0
