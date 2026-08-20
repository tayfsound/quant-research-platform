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
    # Faz 320 — kullanıcı isteği: target_atr_mult/stop_atr_mult oranı
    # gerçek MAE/MFE verisiyle (1098 orta-vadeli kapanmış işlem) yeniden
    # kalibre edildi. LONG'da empirik hedef/stop oranı ~2.75 bulundu (bkz.
    # app_settings_repository.py::DEFAULTS["target_atr_mult_long"] üstündeki
    # not) — LONG varsayılanı artık 6.89x. 100 * 6.89 * 0.02 = 13.78.
    assert abs(ctx.decision.take_profit - 13.78) < 1e-9


def test_risk_target_stage_widens_stop_to_the_min_floor_preserving_the_ratio():
    """Faz 268-sonrası — gerçek bulgu: trade_type'a göre ayrılmış kapanmış
    işlemlerde "scalp" (stop < %4.5) tek başına toplam zararın %92'siydi.
    Düşük daily_atr_pct'te ham stop %4.5 tabanının altına düşerse, SL/TP
    ORANI KORUNARAK genişletilmeli — asla daraltılmamalı."""
    ctx = _ctx(direction="LONG", daily_atr_pct=0.01, current_price=100.0)
    ctx = RiskTargetStage().execute(ctx)

    # Ham: stop=2.5*0.01=%2.5 (taban %4.5'in altında) -> 1.8x ölçeklenir.
    assert abs(ctx.decision.stop_loss - 4.5) < 1e-9  # 100 * %4.5 taban
    assert abs(ctx.decision.take_profit - 12.402) < 1e-9  # 100 * 6.89*0.01*1.8
    # Oran korunmalı: taban öncesi (6.89/2.5) ile taban sonrası aynı.
    ratio_before = (6.89 * 0.01) / (2.5 * 0.01)
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


def test_decision_fusion_no_longer_forces_wait_once_real_targets_are_set(monkeypatch):
    """Bu, gerçek bulgunun kanıtı: RiskTargetStage olmadan (take_profit/
    stop_loss None) DecisionFusion HER ZAMAN ev<=0 -> WAIT üretiyordu.
    RiskTargetStage'in günlük ATR'den kurduğu hedefle, makul bir
    confidence'ta artık pozitif EV ile onaylanabiliyor.

    Faz 268-sonrası: yeni varsayılan oran (1:0.56) breakeven için daha
    yüksek bir kazanma olasılığı gerektiriyor (~%64, eski 1:4 oranın
    %20'sinin tersine) — bu test artık daha yüksek bir confidence/
    strength kullanıyor, hâlâ pozitif EV'nin gerçekten üretildiğini
    kanıtlamak için.

    Faz 268-sonrası (2) — kritik bulgu: bu test paylaşılan quantdb_test
    içindeki decisions tablosundan GERÇEK ZAMANLI hesaplanan confidence
    kalibrasyon eğrisine (services/confidence_calibration.py) yanlışlıkla
    bağımlı hale gelmişti — bu testin amacı RiskTargetStage/DecisionFusion
    EV mantığını doğrulamak, kalibrasyon eğrisinin o an DB'de ne olduğunu
    DEĞİL. Başka testlerin bıraktığı kayıtlara göre eğri değişip bu testi
    sırasına bağlı olarak kırabiliyordu. calibrate_confidence artık ham
    değeri değiştirmeyecek şekilde (boş eğri = fail-closed, zaten
    kalibrasyonun kendi davranışı) sabitleniyor — kalibrasyonun KENDİSİ
    tests/test_confidence_calibration.py'de ayrıca test ediliyor."""
    monkeypatch.setattr("services.decision_fusion.calibrate_confidence", lambda raw_confidence, curve=None: raw_confidence)

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
        AppSettingsRepository(session).set("target_atr_mult_long", "3.0", updated_by="test")
    try:
        ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
        ctx = RiskTargetStage().execute(ctx)
        assert abs(ctx.decision.take_profit - 6.0) < 1e-9  # 100 * 3.0 * 0.02
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("target_atr_mult_long", "6.89", updated_by="test")


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


def _set_adaptive_barrier_ab_test_enabled(value: str) -> None:
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("adaptive_barrier_ab_test_enabled", value, updated_by="test")


def test_adaptive_barrier_ab_test_tags_control_bucket_and_falls_back_to_static(monkeypatch):
    """3. taraf inceleme bulgusu, kullanıcı isteği: adaptive_barrier_
    enabled varsayılan AÇIK olduğu için, barrier tablosu ilk kez
    dolduğu an sistem hiç karşılaştırma fırsatı olmadan %100 adaptive'e
    geçecekti. ab_test açıkken control kovasına düşen bir karar, tablo
    gerçekten var ve eşleşse bile İSTATİSTİKSEL BASELINE için statik
    ATR'ye düşmeli — ve decisions.experiment_bucket'a etiketlenmeli."""
    from analytics.barrier_table_repository import BarrierTableRepository

    stored = {
        "sample_count": 250,
        "group_by": ["direction", "regime", "volatility_regime"],
        "table": {"direction=LONG|regime=bull_trend|volatility_regime=normal": {"sl_pct": 0.06, "tp_pct": 0.05}},
    }
    monkeypatch.setattr(BarrierTableRepository, "get_latest", lambda self: stored)
    monkeypatch.setattr("services.ab_testing.assign_bucket", lambda control_weight=0.5: "control")
    _set_adaptive_barrier_ab_test_enabled("true")
    try:
        ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
        ctx.market.features = {
            "daily_atr_pct": 0.02, "long_term_trend_regime": "bull_trend", "volatility_regime": "normal",
        }
        ctx = RiskTargetStage().execute(ctx)

        assert abs(ctx.decision.stop_loss - 5.0) < 1e-9  # statik: 100 * 2.5 * 0.02, adaptive DEĞİL (6.0)
        entries = [i for i in ctx.cognition.relevant_knowledge if i.get("type") == "experiment_bucket"]
        assert len(entries) == 1
        assert entries[0]["data"]["bucket"] == "adaptive_barrier_v1:control"
    finally:
        _set_adaptive_barrier_ab_test_enabled("false")


def test_adaptive_barrier_ab_test_tags_treatment_bucket_and_uses_adaptive(monkeypatch):
    """AYNI test, treatment kovası — gerçekten adaptive öneriyi kullanmalı
    ve 'adaptive_barrier_v1:treatment' olarak etiketlenmeli."""
    from analytics.barrier_table_repository import BarrierTableRepository

    stored = {
        "sample_count": 250,
        "group_by": ["direction", "regime", "volatility_regime"],
        "table": {"direction=LONG|regime=bull_trend|volatility_regime=normal": {"sl_pct": 0.06, "tp_pct": 0.05}},
    }
    monkeypatch.setattr(BarrierTableRepository, "get_latest", lambda self: stored)
    monkeypatch.setattr("services.ab_testing.assign_bucket", lambda control_weight=0.5: "treatment")
    _set_adaptive_barrier_ab_test_enabled("true")
    try:
        ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
        ctx.market.features = {
            "daily_atr_pct": 0.02, "long_term_trend_regime": "bull_trend", "volatility_regime": "normal",
        }
        ctx = RiskTargetStage().execute(ctx)

        assert abs(ctx.decision.stop_loss - 6.0) < 1e-9  # adaptive: 100 * 0.06
        entries = [i for i in ctx.cognition.relevant_knowledge if i.get("type") == "experiment_bucket"]
        assert len(entries) == 1
        assert entries[0]["data"]["bucket"] == "adaptive_barrier_v1:treatment"
    finally:
        _set_adaptive_barrier_ab_test_enabled("false")


def test_adaptive_barrier_ab_test_disabled_by_default_no_tagging():
    """Varsayılan (ab_test kapalı) — hiçbir experiment_bucket etiketi
    eklenmemeli, mevcut statik davranış hiç değişmemeli (regresyon
    kilidi)."""
    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
    ctx = RiskTargetStage().execute(ctx)

    entries = [i for i in ctx.cognition.relevant_knowledge if i.get("type") == "experiment_bucket"]
    assert entries == []


def test_risk_target_stage_skips_all_work_when_final_size_is_zero(monkeypatch):
    """3. taraf inceleme bulgusu, doğrulandı: MetaStage WAIT dediğinde
    (final_size=0) bile proposed_direction genelde LONG/SHORT kalıyordu
    (belief.direction her zaman set edilir) — bu, watchlist'teki her WAIT
    kararında 2 gereksiz DB sorgusuna (_load_multipliers + _try_adaptive_
    barrier) yol açıyordu. Artık final_size<=0 anında çıkmalı, hiçbir DB
    sorgusu yapmamalı."""
    called = []
    monkeypatch.setattr(
        "database.repositories.app_settings_repository.AppSettingsRepository.get",
        lambda self, key: called.append(key) or "0",
    )

    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
    ctx.decision.final_size = 0.0  # MetaStage WAIT'i taklit ediyor

    result = RiskTargetStage().execute(ctx)

    assert result.decision.stop_loss is None
    assert result.decision.take_profit is None
    assert called == []


# Faz 299-300 — kullanıcı isteği: TP/SL Confluence canlıya bağlandı
# ("wire edelim"). SADECE hedefi (stop'u değil) gerçek bir yapısal
# bölgeye (>=2 bağımsız yöntem) yakınsa daha erken/gerçekçi bir noktaya
# çekiyor — asla hedefi mevcut ATR hesabından daha UZAĞA taşımıyor.

def test_risk_target_stage_snaps_target_to_confluence_zone_when_present():
    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
    # Ham hedef: 100 * 6.89 * 0.02 = 13.78 -> fiyat 113.78. Aralarında
    # (100-113.78) 2 bağımsız yöntemin birleştiği gerçek bir bölge: 101.5.
    ctx.market.features["confluence_zones"] = [
        {"level": 101.5, "method_count": 2, "contributing_methods": ["sr_resistance", "pivot_r1"]}
    ]
    result = RiskTargetStage().execute(ctx)

    # Hedef artık 113.78 DEĞİL, 101.5'in hemen altına çekilmiş olmalı.
    assert result.decision.take_profit < 13.78
    assert 1.0 < result.decision.take_profit < 1.5  # (101.5*(1-eps) - 100) civarı
    # Stop HİÇ etkilenmemeli.
    assert abs(result.decision.stop_loss - 5.0) < 1e-9


def test_risk_target_stage_ignores_confluence_zone_beyond_target():
    """Bölge hedefin ÖTESİNDEYSE (aradan geçilmesi gerekmiyor) hedef
    hiç değişmemeli — mevcut davranış (regresyon yok)."""
    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
    ctx.market.features["confluence_zones"] = [
        {"level": 150.0, "method_count": 2, "contributing_methods": ["sr_resistance", "pivot_r1"]}
    ]
    result = RiskTargetStage().execute(ctx)
    assert abs(result.decision.take_profit - 13.78) < 1e-9


def test_risk_target_stage_ignores_weak_confluence_zone():
    """method_count<2 (tek yöntem) — ayırt edici değil, hedef değişmemeli."""
    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
    ctx.market.features["confluence_zones"] = [
        {"level": 101.5, "method_count": 1, "contributing_methods": ["sr_resistance"]}
    ]
    result = RiskTargetStage().execute(ctx)
    assert abs(result.decision.take_profit - 13.78) < 1e-9


def test_risk_target_stage_without_confluence_zones_feature_behaves_as_before():
    """confluence_zones hiç yoksa (ör. hesaplama başarısız olup boş liste
    döndüyse) mevcut davranış hiç değişmemeli — fail-closed."""
    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
    result = RiskTargetStage().execute(ctx)
    assert abs(result.decision.take_profit - 13.78) < 1e-9


def test_risk_target_stage_snaps_short_target_to_confluence_zone():
    ctx = _ctx(direction="SHORT", daily_atr_pct=0.02, current_price=100.0)
    # Ham hedef: 100 - 2.8 = 97.2. Aralarında (97.2-100) gerçek bir bölge: 98.5.
    ctx.market.features["confluence_zones"] = [
        {"level": 98.5, "method_count": 2, "contributing_methods": ["sr_support", "volume_profile_poc"]}
    ]
    result = RiskTargetStage().execute(ctx)
    assert result.decision.take_profit < 2.8
    assert 1.0 < result.decision.take_profit < 1.5


def test_risk_target_stage_snaps_stop_to_confluence_zone_when_present():
    """Faz 317-sonrası — kullanıcı bulgusu: "SL'de de faydalı olmaz
    mıydı o veri?" Ham stop: 100 * (1 - 0.05) = 95.0 (min_stop_pct
    tabanı 0.045 -> 95.5, henüz devrede değil çünkü 0.05 > 0.045).
    Aradaki (95.0-100) 2 bağımsız yöntemin birleştiği gerçek bir
    destek: 95.3 — stop fiyata daha YAKIN bir noktaya (95.3'ün hemen
    altına, ama hâlâ taban 0.045'in ÜSTÜNDE) çekilmeli."""
    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
    ctx.market.features["confluence_zones"] = [
        {"level": 95.3, "method_count": 2, "contributing_methods": ["sr_support", "pivot_s1"]}
    ]
    result = RiskTargetStage().execute(ctx)

    # Stop artık 5.0 (100-95) DEĞİL, 95.3'ün hemen altına çekilmiş —
    # fiyata olan mesafesi KÜÇÜLMÜŞ, ama taban (4.5) hâlâ AŞILMAMIŞ.
    assert 4.5 < result.decision.stop_loss < 5.0
    # Hedef HİÇ etkilenmemeli (bu senaryoda hedef aralığında zone yok).
    assert abs(result.decision.take_profit - 13.78) < 1e-9


def test_risk_target_stage_snaps_short_stop_to_confluence_zone():
    ctx = _ctx(direction="SHORT", daily_atr_pct=0.02, current_price=100.0)
    # Ham stop: 100 * 1.05 = 105.0. Aradaki (100-105) gerçek bir bölge: 104.7.
    ctx.market.features["confluence_zones"] = [
        {"level": 104.7, "method_count": 2, "contributing_methods": ["sr_resistance", "volume_profile_poc"]}
    ]
    result = RiskTargetStage().execute(ctx)
    assert 4.5 < result.decision.stop_loss < 5.0


def test_risk_target_stage_stop_confluence_never_breaches_the_min_stop_pct_floor(monkeypatch):
    """Kritik güvenlik testi: Faz 268-sonrası'nın min_stop_pct tabanı
    (gerçek olay: "scalp bölgesi" tek başına toplam zararın %92'sini
    oluşturmuştu) confluence'tan da MUAF DEĞİL — gerçek bir yapısal
    seviye bile olsa, stop bu tabanın altına asla inmemeli."""
    from database.repositories.app_settings_repository import AppSettingsRepository
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("min_stop_pct", "0.045", updated_by="test")

    try:
        ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
        # Ham stop zaten min_stop_pct tabanına (100*(1-0.045)=95.5) çekilmiş
        # olacak. Confluence bölgesi bu tabanın da İÇİNDE (99.0) — taban
        # olmasaydı stop fiyata çok daha yakına (99.0 civarı) çekilirdi.
        ctx.market.features["confluence_zones"] = [
            {"level": 99.0, "method_count": 2, "contributing_methods": ["sr_support", "pivot_s1"]}
        ]
        result = RiskTargetStage().execute(ctx)

        # Stop tabanın (4.5) altına ASLA inmemeli.
        assert result.decision.stop_loss >= 4.5 - 1e-9
    finally:
        with SessionFactory.get_session() as session:
            from database.repositories.app_settings_repository import DEFAULTS
            AppSettingsRepository(session).set("min_stop_pct", DEFAULTS["min_stop_pct"], updated_by="test")


def test_risk_target_stage_ignores_confluence_zone_beyond_stop():
    """Bölge stop'un ÖTESİNDEYSE (fiyattan stop'a giden yolda
    karşılaşılmıyor) stop hiç değişmemeli."""
    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
    ctx.market.features["confluence_zones"] = [
        {"level": 50.0, "method_count": 2, "contributing_methods": ["sr_support", "pivot_s1"]}
    ]
    result = RiskTargetStage().execute(ctx)
    assert abs(result.decision.stop_loss - 5.0) < 1e-9


def test_risk_target_stage_ignores_weak_confluence_zone_for_stop():
    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, current_price=100.0)
    ctx.market.features["confluence_zones"] = [
        {"level": 97.5, "method_count": 1, "contributing_methods": ["sr_support"]}
    ]
    result = RiskTargetStage().execute(ctx)
    assert abs(result.decision.stop_loss - 5.0) < 1e-9


def test_decision_fusion_still_forces_wait_without_risk_target_stage():
    """Regresyon kilidi: RiskTargetStage atlanırsa (eski, bug'lı davranış)
    DecisionFusion hâlâ her zaman WAIT'e zorlamalı — bu testin kendisi
    orijinal bug'ı belgeliyor."""
    ctx = _ctx(direction="LONG", daily_atr_pct=0.02, confidence=0.9)
    # RiskTargetStage.execute() KASITLI OLARAK çağrılmıyor.

    ctx = DecisionFusion().evaluate(ctx, _belief(direction="LONG", strength=0.9))

    assert ctx.decision.action.value == "WAIT"
    assert ctx.decision.final_size == 0.0
