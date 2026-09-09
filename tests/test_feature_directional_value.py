"""Faz 462 — analytics/feature_directional_value.py birim testleri."""
import math

from analytics.feature_directional_value import compute_feature_directional_value


def _num(feature, value, up_n, down_n, day="2026-09-01"):
    return (
        [{"feature": feature, "value": value, "forward_label": "UP", "day": day}] * up_n
        + [{"feature": feature, "value": value, "forward_label": "DOWN", "day": day}] * down_n
    )


def _cat(feature, value, up_n, down_n):
    return _num(feature, value, up_n, down_n)


def test_numeric_feature_positive_separation():
    """Yüksek değerlerde daha çok yükseliş -> doğru işaretli sayısal
    özellik."""
    records = _num("rsi_slope", 10.0, 300, 100) + _num("rsi_slope", -10.0, 100, 300)
    result = compute_feature_directional_value(records)
    f = result["features"]["rsi_slope"]

    assert f["kind"] == "numeric"
    assert f["verdict"] == "correct_sign"
    assert math.isclose(f["separation"], 0.75 - 0.25, abs_tol=1e-6)


def test_numeric_feature_inverted_separation():
    records = _num("momentum", 10.0, 100, 300) + _num("momentum", -10.0, 300, 100)
    result = compute_feature_directional_value(records)
    assert result["features"]["momentum"]["verdict"] == "inverted"


def test_monotonicity_flag_detects_strengthening_at_the_extremes():
    """Faz 461'de taker akışında kullanılan AYNI ölçüt: gerçek bilgi
    uçlarda GÜÇLENİR. Burada en uç %10, çeyrekliklerden daha güçlü bir
    ayrım vermeli."""
    records = []
    # Uc degerler cok guclu, orta degerler zayif.
    records += _num("flow_z", 3.0, 280, 20)
    records += _num("flow_z", 1.0, 160, 140)
    records += _num("flow_z", -1.0, 140, 160)
    records += _num("flow_z", -3.0, 20, 280)

    f = compute_feature_directional_value(records)["features"]["flow_z"]

    assert f["monotonic"] is True
    assert abs(f["extreme_separation"]) > abs(f["separation"])


def test_numeric_feature_inside_neutral_band_is_no_signal():
    records = _num("atr", 10.0, 201, 199) + _num("atr", 1.0, 199, 201)
    assert compute_feature_directional_value(records)["features"]["atr"]["verdict"] == "no_signal"


def test_categorical_feature_reports_discrimination():
    """Faz 436'nın order_flow_relationship'inin gerçek veride ölçülen
    deseni: "bullish" kategorilerinde P(UP) DÜŞÜK, "bearish"te YÜKSEK."""
    records = []
    records += _cat("order_flow_relationship_category", "bullish_new_longs", 120, 180)
    records += _cat("order_flow_relationship_category", "bearish_long_capitulation", 170, 130)
    records += _cat("order_flow_relationship_category", "unclear", 150, 150)

    f = compute_feature_directional_value(records)["features"]["order_flow_relationship_category"]

    assert f["kind"] == "categorical"
    assert f["verdict"] == "discriminative"
    assert f["highest_p_up"]["category"] == "bearish_long_capitulation"
    assert f["lowest_p_up"]["category"] == "bullish_new_longs"
    assert math.isclose(f["separation"], 170/300 - 120/300, abs_tol=1e-6)


def test_categorical_feature_needs_two_eligible_categories():
    """Tek kategorili (ör. hep "unclear") bir alan ayırt edici olamaz."""
    records = _cat("liquidation_pressure_category", "no_data", 300, 300)
    records += _cat("liquidation_pressure_category", "long_squeeze", 5, 5)

    f = compute_feature_directional_value(records)["features"]["liquidation_pressure_category"]

    assert f["usable"] is False
    assert f["separation"] is None
    # Yetersiz kategori yine de RAPORDA gorunmeli, sessizce kaybolmamali.
    assert "long_squeeze" in f["categories"]


def test_booleans_are_treated_as_categorical_not_numeric():
    """`isinstance(True, int)` Python'da True -- ama True/False bir ölçek
    değil, bayraktır. Sayısal muamele çeyreklik hesabını anlamsız
    kılardı."""
    records = _cat("regime_changepoint_detected", True, 100, 200)
    records += _cat("regime_changepoint_detected", False, 200, 100)

    f = compute_feature_directional_value(records)["features"]["regime_changepoint_detected"]
    assert f["kind"] == "categorical"


def test_constant_numeric_feature_fails_closed():
    """Değeri hiç değişmeyen bir özellikte çeyreklik ayrımı tanımsız."""
    records = _num("data_quality_score", 1.0, 300, 300)
    f = compute_feature_directional_value(records)["features"]["data_quality_score"]
    assert f["separation"] is None
    assert f["usable"] is False


def test_thin_numeric_feature_is_marked_unusable():
    records = _num("onchain_solana_tps", 100.0, 50, 50) + _num("onchain_solana_tps", 1.0, 50, 50)
    f = compute_feature_directional_value(records)["features"]["onchain_solana_tps"]
    assert f["usable"] is False
    assert f["verdict"] is None


def test_ranking_orders_by_absolute_strength():
    """Ters işaretli güçlü bir sinyal, zayıf doğru işaretliden DAHA
    önemlidir -- sıralama mutlak değere göre olmalı."""
    records = _num("zayif", 10.0, 210, 190) + _num("zayif", 1.0, 190, 210)
    records += _num("guclu_ters", 10.0, 100, 300) + _num("guclu_ters", 1.0, 300, 100)

    ranked = compute_feature_directional_value(records)["ranked_by_strength"]
    assert ranked[0] == "guclu_ters"


def test_none_values_are_excluded():
    records = _num("rsi_divergence", None, 300, 300)
    assert compute_feature_directional_value(records) is None


# --- Faz 463: piyasa-geneli ozellik ayiklama (kullanici istegi: "kanit lazim bize") ---

def _rec(feature, value, label, day="2026-09-01", bucket=None, symbol=None):
    return {
        "feature": feature, "value": value, "forward_label": label,
        "day": day, "time_bucket": bucket, "symbol": symbol,
    }


def test_market_wide_feature_is_rejected_because_it_cannot_separate_symbols():
    """KULLANICI TEŞHİSİ (2026-09-09): "bütün sembollerde aynı değeri
    alıyor dediklerin onchain verisi." Doğru — onchain özellikleri
    belirli bir ANDA tüm sembollerde aynı değeri alır.

    Böyle bir özellik ham ayrımda GÜÇLÜ görünebilir (çünkü zaman içi
    piyasa dalgalanmasını yakalar) ama sembol-içi ayrımı hesaplanamaz:
    hiçbir zaman kovasında varyans yoktur. `proven` ASLA True olmamalı."""
    records = []
    for i, (deger, gun) in enumerate([
        (100.0, "2026-09-01"), (100.0, "2026-09-02"), (100.0, "2026-09-03"),
        (10.0, "2026-09-04"), (10.0, "2026-09-05"), (10.0, "2026-09-06"),
    ]):
        # Her kovada TUM semboller AYNI degeri aliyor (piyasa geneli).
        label_up, label_down = (90, 10) if deger == 100.0 else (10, 90)
        for j in range(label_up):
            records.append(_rec("onchain_hash_rate", deger, "UP", gun, f"b{i}", f"S{j%12}"))
        for j in range(label_down):
            records.append(_rec("onchain_hash_rate", deger, "DOWN", gun, f"b{i}", f"S{j%12}"))

    f = compute_feature_directional_value(records)["features"]["onchain_hash_rate"]

    # Ham ayrim DEVASA gorunuyor...
    assert abs(f["separation"]) > 0.5
    # ...ama sembol-ici hicbir kovada varyans yok.
    assert f["within_symbol"]["varying_buckets"] == 0
    assert f["within_symbol"]["symbol_specific"] is False
    # Dolayisiyla KANITLANMIS sayilmaz.
    assert f["proven"] is False


def test_symbol_specific_feature_survives_the_within_bucket_test():
    """Gerçek sembol-bazlı bir özellik: AYNI anda semboller arasında
    değişiyor ve yön ayrımı kova içinde de korunuyor."""
    records = []
    for i in range(8):
        gun = f"2026-09-0{(i % 6) + 1}"
        for j in range(30):
            # Yuksek deger -> yukselis, dusuk deger -> dusus (kova ICINDE).
            records.append(_rec("rsi_percentile", 90.0, "UP", gun, f"b{i}", f"S{j}"))
            records.append(_rec("rsi_percentile", 90.0, "DOWN", gun, f"b{i}", f"S{j}") if j % 4 == 0 else
                           _rec("rsi_percentile", 90.0, "UP", gun, f"b{i}", f"S{j}"))
            records.append(_rec("rsi_percentile", 10.0, "DOWN", gun, f"b{i}", f"S{j}"))
            records.append(_rec("rsi_percentile", 10.0, "UP", gun, f"b{i}", f"S{j}") if j % 4 == 0 else
                           _rec("rsi_percentile", 10.0, "DOWN", gun, f"b{i}", f"S{j}"))

    f = compute_feature_directional_value(records)["features"]["rsi_percentile"]

    assert f["within_symbol"]["symbol_specific"] is True
    assert f["within_symbol"]["separation"] > 0.02
    assert f["proven"] is True


def test_proven_requires_within_symbol_separation_to_agree_in_sign():
    """Ham ayrım pozitif ama sembol-içi ayrım NEGATİF ise, ham sonuç
    piyasa zamanlamasından geliyor demektir — çelişki varsa
    kanıtlanmamış sayılır."""
    records = []
    for i in range(8):
        gun = f"2026-09-0{(i % 6) + 1}"
        # Kova ICINDE yuksek deger -> DUSUS (ham egilimin TERSI)
        for j in range(30):
            records.append(_rec("celiskili", 90.0, "DOWN", gun, f"b{i}", f"S{j}"))
            records.append(_rec("celiskili", 10.0, "UP", gun, f"b{i}", f"S{j}"))
        # Ama kovalar arasi: yuksek kovalar cogunlukla UP
        if i % 2 == 0:
            for j in range(40):
                records.append(_rec("celiskili", 95.0, "UP", gun, f"b{i}", f"S{j}"))

    f = compute_feature_directional_value(records)["features"]["celiskili"]
    if f["separation"] is not None and f["within_symbol"]["separation"] is not None:
        if f["separation"] * f["within_symbol"]["separation"] < 0:
            assert f["proven"] is False


def test_within_symbol_is_none_without_time_buckets():
    """Zaman kovası bilgisi yoksa sembol-içi test YAPILAMAZ — "temiz"
    varsaymak uydurma güvence olurdu, `proven` False kalmalı."""
    records = _num("bir_ozellik", 10.0, 300, 100) + _num("bir_ozellik", 1.0, 100, 300)
    f = compute_feature_directional_value(records)["features"]["bir_ozellik"]
    assert f["within_symbol"] is None
    assert f["proven"] is False


def test_daily_consistency_rejects_a_one_day_fluke():
    """Tek bir günde çok güçlü, diğer günlerde ters olan bir özellik
    kanıtlanmış sayılmamalı."""
    records = []
    for gun, (u, d) in [("2026-09-01", (280, 20)), ("2026-09-02", (100, 200)),
                        ("2026-09-03", (100, 200)), ("2026-09-04", (100, 200))]:
        for _ in range(u):
            records.append(_rec("kaza", 90.0, "UP", gun, "b1", "S1"))
        for _ in range(d):
            records.append(_rec("kaza", 90.0, "DOWN", gun, "b1", "S1"))
        for _ in range(d):
            records.append(_rec("kaza", 10.0, "UP", gun, "b1", "S1"))
        for _ in range(u):
            records.append(_rec("kaza", 10.0, "DOWN", gun, "b1", "S1"))

    f = compute_feature_directional_value(records)["features"]["kaza"]
    if f["daily"] is not None:
        assert f["daily"]["consistent"] is False
    assert f["proven"] is False


def test_categorical_features_also_get_the_within_symbol_test():
    """BİR KUSURDAN ÖĞRENİLDİ: ilk sürümde sembol-içi test SADECE
    sayısal özelliklere uygulanıyordu. Sonuç: `trend` ve `ema_alignment`
    gibi -- Faz 460'ta `market_regime`'in %100 kopyası olduğu KANITLANMIŞ
    -- kategorik sinyaller dört şartın yalnızca ikisini geçerek
    "kanıtlanmış" görünüyordu.

    Burada rejim-kopyası bir kategorik alan taklit ediliyor: her zaman
    kovasında TÜM semboller aynı kategoriye düşer. Kanıtlanmış
    sayılmamalı."""
    records = []
    for i in range(8):
        gun = f"2026-09-0{(i % 6) + 1}"
        kategori = "bullish" if i % 2 == 0 else "bearish"
        up, down = (60, 40) if kategori == "bullish" else (40, 60)
        for j in range(up):
            records.append(_rec("rejim_kopyasi", kategori, "UP", gun, f"b{i}", f"S{j}"))
        for j in range(down):
            records.append(_rec("rejim_kopyasi", kategori, "DOWN", gun, f"b{i}", f"S{j}"))

    f = compute_feature_directional_value(records)["features"]["rejim_kopyasi"]

    assert f["kind"] == "categorical"
    # Ayirt edici GORUNUYOR...
    assert f["separation"] > 0.02
    # ...ama hicbir zaman kovasinda kategori DEGISMIYOR.
    assert f["within_symbol"]["varying_buckets"] == 0
    assert f["within_symbol"]["symbol_specific"] is False
    assert f["proven"] is False


def test_genuinely_symbol_specific_categorical_is_proven():
    """Aynı anda semboller FARKLI kategorilere düşüyor ve ayrım kova
    içinde de korunuyor -> kanıtlanmış."""
    records = []
    for i in range(8):
        gun = f"2026-09-0{(i % 6) + 1}"
        for j in range(50):
            # AYNI kovada iki kategori birden var.
            records.append(_rec("of_kategori", "bearish_capitulation", "UP", gun, f"b{i}", f"S{j}"))
            if j % 3 == 0:
                records.append(_rec("of_kategori", "bearish_capitulation", "DOWN", gun, f"b{i}", f"S{j}"))
            records.append(_rec("of_kategori", "bullish_new_longs", "DOWN", gun, f"b{i}", f"S{j}"))
            if j % 3 == 0:
                records.append(_rec("of_kategori", "bullish_new_longs", "UP", gun, f"b{i}", f"S{j}"))

    f = compute_feature_directional_value(records)["features"]["of_kategori"]

    assert f["within_symbol"]["symbol_specific"] is True
    assert f["within_symbol"]["separation"] > 0.02
    assert f["proven"] is True
