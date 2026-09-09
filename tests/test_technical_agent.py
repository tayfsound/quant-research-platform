"""Technical Agent testleri."""
import re

from agents.technical_agent import TechnicalAgent
from contracts.technical import TechnicalContext


def test_bullish_setup_now_votes_short_because_that_is_what_was_measured():
    agent = TechnicalAgent()
    # Faz 468 — rsi_value EKLENDI: market_structure artik shadow'da
    # (string uyusmazligi yuzunden zaten hic skorlanmiyordu), momentum ve
    # ema_alignment da Faz 423'ten beri shadow. Yani bu fikstürde GERCEKTEN
    # skorlanan tek yonlu sinyal `trend` kaliyordu ve 1.0, yon esigini
    # (>0.5) volume_confirmation cezasindan (-0.3) sonra ancak siyiriyordu.
    # rsi_extreme (asiri satim) gercek, olcumde DOGRU isaretli (+0,150)
    # bir sinyal -- fikstürü onunla saglamlastiriyoruz.
    ctx = TechnicalContext(
        trend="bullish",
        momentum="strengthening",
        market_structure="higher_highs_higher_lows",
        volume_confirmation=True,
        ema_alignment="bullish_aligned",
        rsi_value=20.0,
    )
    opinion = agent.analyze(ctx)
    # FAZ 480 — BU TESTIN ILK HALI "bullish -> LONG" diyordu; o VARSAYIM
    # gercek veriyle YANLISLANDI ve trend_weight -1.0'a cevrildi.
    # Kanit: sinyal seviyesinde separation -0,096, gunluk tutarlilik 5/5;
    # baglam ozelligi olarak trend=bullish -> P(1sa UP)=0,488 (bearish
    # 0,592), sembol-ici ayrim +0,036. Ayrica Faz 472'de Council'in
    # SADECE rejime KARSI konustugunda guvenilir oldugu, Faz 478'de risk
    # simulatorunun en kotu diliminin SHORT ciktigi bulundu.
    #
    # rsi_extreme (asiri satim, +1.0, DOGRU isaretli) trend'in -1.0'ini
    # dengeliyor; yonu belirleyen kalan katkilar.
    assert opinion.direction in ("SHORT", "WAIT")
    assert opinion.feature_contributions["trend"] < 0
    assert len(opinion.evidence) >= 2

def test_bearish_setup_now_leans_long():
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="bearish",
        momentum="weakening",
        market_structure="lower_highs_lower_lows",
        rsi_value=80.0,
    )
    opinion = agent.analyze(ctx)
    # FAZ 480 — aynadaki hali: bearish trend artik POZITIF katki veriyor
    # (olculen P(1sa UP)=0,592). rsi_value=80 (asiri alim) rsi_extreme'i
    # -1.0 yapiyor ve trend'in +1.0'ini dengeliyor.
    assert opinion.feature_contributions["trend"] > 0
    assert opinion.direction in ("LONG", "WAIT")

def test_ranging_market_waits():
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="neutral",
        momentum="neutral",
        market_structure="ranging",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "WAIT"

def test_volume_confirmation_no_longer_rewarded_as_bullish():
    """Faz 258: kritik bulgu — feature importance analizi (561 gerçek
    kapanmış işlem) volume_confirmation=True'nun aslında DAHA KÖTÜ
    sonuçla ilişkili olduğunu gösterdi (%15.4 vs %28.5 kazanma oranı).
    Bu test, volume_confirmation=True'nun artık bullish bir teyit olarak
    puanlanmadığını (aksine hafif negatif) kanıtlıyor."""
    agent = TechnicalAgent()

    ctx_with_spike = TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs_higher_lows",
        volume_confirmation=True,
    )
    ctx_without_spike = TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs_higher_lows",
        volume_confirmation=False,
    )

    opinion_with_spike = agent.analyze(ctx_with_spike)
    opinion_without_spike = agent.analyze(ctx_without_spike)

    assert not any("teyit ediyor" in e for e in opinion_with_spike.evidence)
    assert any("hacim sıçraması" in c.lower() for c in opinion_with_spike.caveats)
    # Aynı diğer koşullarda, hacim sıçraması OLAN senaryo artık OLMAYANDAN
    # daha düşük konviksiyonlu olmalı (önceden tam tersiydi).
    # Faz 480 -- yon-agnostik hale getirildi. Eskiden "confidence duser"
    # deniyordu ama bu SADECE taban yon LONG iken gecerliydi; trend'in
    # isareti cevrilince (bkz. TechnicalAgentCoefficients.trend_weight)
    # negatif bir katki SHORT'u GUCLENDIRIYOR ve |skor| buyuyor.
    # Testin ASIL iddiasi zaten katkinin NEGATIF olmasi: hacim sicramasi
    # bullish bir teyit DEGIL (Faz 258, 561 islem: %15,4 vs %28,5).
    assert opinion_with_spike.feature_contributions["volume_confirmation"] < 0
    assert "volume_confirmation" not in opinion_without_spike.feature_contributions


def test_volume_divergence_warning():
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="bullish",
        momentum="strengthening",
        market_structure="higher_highs_higher_lows",
        volume_confirmation=False,
    )
    opinion = agent.analyze(ctx)
    assert any("Hacim trendi teyit etmiyor" in c for c in opinion.caveats)


def test_confirming_tradingview_signal_adds_evidence_not_a_new_direction():
    """Faz 193: TradingView ikinci görüş — kendi hesapladığı yönü teyit
    ederse evidence'a eklenir, yönü DEĞİŞTİRMEZ."""
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        # Faz 480 -- trend'in isareti cevrildigi icin bu baglamda ajanin
        # KENDI yonu artik SHORT; "teyit eden" dis sinyal de bearish olmali.
        trend="bullish", momentum="strengthening", market_structure="higher_highs_higher_lows",
        external_signal="bearish", external_signal_source="tradingview",
    )
    opinion = agent.analyze(ctx)
    # Faz 480 -- bu test TradingView MEKANIZMASINI olcuyor, trend'in
    # isaretini degil: dis sinyal EVIDENCE ekler, YONU DEGISTIRMEZ.
    # Yon-agnostik hale getirildi ki isaret degisiklikleri onu bir daha
    # dolayli olarak kirmasin.
    without_tv = agent.analyze(TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs_higher_lows",
    ))
    assert opinion.direction == without_tv.direction
    assert any("TradingView" in e for e in opinion.evidence)


def test_conflicting_tradingview_signal_adds_caveat_not_a_direction_flip():
    """TradingView kendi iç görüşle çelişirse sadece bir uyarı (caveat)
    eklenir — tek başına yönü LONG'dan SHORT'a çevirmez."""
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        # Faz 480 -- ajanin kendi yonu artik SHORT; "celisen" dis sinyal
        # bullish olmali.
        trend="bullish", momentum="strengthening", market_structure="higher_highs_higher_lows",
        external_signal="bullish", external_signal_source="tradingview",
    )
    opinion = agent.analyze(ctx)
    # Faz 480 -- yon-agnostik: celisen dis sinyal SADECE caveat ekler,
    # ajanin KENDI yonunu degistirmez.
    without_tv = agent.analyze(TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs_higher_lows",
    ))
    assert opinion.direction == without_tv.direction
    assert any("çelişiyor" in c for c in opinion.caveats)


def test_no_external_signal_means_no_extra_evidence_or_caveat():
    agent = TechnicalAgent()
    ctx = TechnicalContext(trend="bullish", momentum="strengthening", market_structure="higher_highs_higher_lows")
    opinion = agent.analyze(ctx)
    assert not any("TradingView" in e for e in opinion.evidence)
    assert not any("TradingView" in c for c in opinion.caveats)


def test_feature_contributions_sum_to_the_implied_raw_score():
    """Faz 268-sonrası: Feature Importance — feature_contributions her
    zaman GERÇEK score'a (confidence = min(|score|/5.0, 0.85)) eşit
    toplanmalı, tıpkı QuantAgent'ta olduğu gibi.

    Faz 423 — momentum/ema_alignment artık trend ile %100 redundant
    oldukları için shadow (skora katkısı yok) — implied score SADECE
    gerçekten skora giren feature'ları kapsamalı.

    Faz 468 — market_structure de shadow'a katıldı (string uyuşmazlığı
    yüzünden zaten YILLARDIR hiç skorlanmıyordu; düzeltilirken ölçülen
    TERS işaretle skora sokulmadı, bkz. agents/technical_agent.py)."""
    agent = TechnicalAgent()
    opinion = agent.analyze(TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs_higher_lows",
        ema_alignment="bullish_aligned", adx=10.0,
    ))
    shadow_keys = {"momentum", "ema_alignment", "bollinger_confirm",
                   "adx_strong_confirm", "market_structure"}
    implied_score = sum(v for k, v in opinion.feature_contributions.items() if k not in shadow_keys)
    assert abs(abs(implied_score) - opinion.confidence * 5.0) < 1e-6


def test_feature_contributions_are_empty_when_no_signal_fires():
    agent = TechnicalAgent()
    opinion = agent.analyze(TechnicalContext())  # tüm varsayılanlar -> hiçbir dal tetiklenmez
    assert opinion.feature_contributions == {}


def test_feature_contributions_names_the_active_signals():
    agent = TechnicalAgent()
    opinion = agent.analyze(TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs_higher_lows",
        ema_alignment="bullish_aligned", adx=30.0, di_plus=30.0, di_minus=10.0,
    ))
    # Faz 480 -- bu test hangi sinyallerin ATESLENDIGINI olcuyor, isaretini
    # degil. trend artik negatif katki veriyor (olculen: bullish -> dusus
    # egilimi), o yuzden "0'dan farkli" kontrolu yapiliyor.
    for ad in ("trend", "momentum", "market_structure", "ema_alignment", "adx_strong_confirm"):
        assert opinion.feature_contributions[ad] != 0, ad


def test_feature_contributions_reflect_the_adx_weak_discount():
    """ADX<20 iken scale_all(adx_weak_discount) O ANA KADAR birikmiş TÜM
    katkılara uygulanmalı — orijinal `score *= c.adx_weak_discount` ile
    birebir aynı sıralama/etki."""
    agent = TechnicalAgent()
    no_discount = agent.analyze(TechnicalContext(trend="bullish", adx=22.0))
    with_discount = agent.analyze(TechnicalContext(trend="bullish", adx=10.0))
    assert abs(with_discount.feature_contributions["trend"] - no_discount.feature_contributions["trend"] * 0.7) < 1e-6


def test_htf_agreement_discounts_confidence_but_never_changes_direction():
    """Faz 316 — gerçek geçmiş veri ölçümü: kısa-vadeli yön 4h trendle
    AYNIYKEN kazanma oranı daha düşük (%41.6) — confidence indirilmeli,
    direction ASLA değişmemeli."""
    agent = TechnicalAgent()
    base_ctx = TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs_higher_lows",
        ema_alignment="bullish_aligned",
    )
    baseline = agent.analyze(base_ctx)
    # Faz 480 -- "uyusan" HTF, ajanin KENDI yonune gore secilmeli. trend'in
    # isareti cevrildigi icin bu baglamda ajan artik SHORT diyor, dolayisiyla
    # uyusan ust-zaman-dilimi trendi "bearish". Sabit "bullish" yazmak,
    # testi yanlislikla DISAGREEMENT kolunu olcer hale getiriyordu.
    uyusan = "bullish" if baseline.direction == "LONG" else "bearish"
    agreeing = agent.analyze(base_ctx.model_copy(update={"higher_timeframe_trend": uyusan}))

    # Faz 480 -- yon-agnostik. Bu test HTF MEKANIZMASINI olcuyor
    # (confidence degisir, YON ASLA degismez), trend'in isaretini degil.
    assert baseline.direction in ("LONG", "SHORT")
    assert agreeing.direction == baseline.direction
    assert agreeing.confidence < baseline.confidence
    assert abs(agreeing.confidence - round(baseline.confidence * 0.75, 3)) < 1e-3


def test_htf_disagreement_boosts_confidence_but_never_changes_direction():
    """Aynı ölçüm: kısa-vadeli yön 4h trendin TERSİNDEYKEN kazanma oranı
    daha yüksek (%74.7) — confidence artırılmalı (0.85 tavanı korunarak),
    direction ASLA değişmemeli."""
    agent = TechnicalAgent()
    # Faz 480 -- rsi_value=80 KALDIRILDI: trend'in isareti cevrilince
    # bearish trend +1.0, rsi_extreme (asiri alim) -1.0 veriyordu ve skor
    # TAM SIFIRA (WAIT) dusuyordu. Bu test HTF mekanizmasini olcuyor,
    # yonlu bir taban skora ihtiyaci var.
    base_ctx = TechnicalContext(
        trend="bearish", momentum="weakening", market_structure="lower_highs_lower_lows",
    )
    baseline = agent.analyze(base_ctx)
    # Faz 480 -- "celisen" HTF de ajanin KENDI yonune gore secilmeli.
    celisen = "bearish" if baseline.direction == "LONG" else "bullish"
    disagreeing = agent.analyze(base_ctx.model_copy(update={"higher_timeframe_trend": celisen}))

    assert baseline.direction in ("LONG", "SHORT")
    assert disagreeing.direction == baseline.direction
    assert disagreeing.confidence >= baseline.confidence
    assert disagreeing.confidence <= 0.85


def test_htf_trend_missing_or_neutral_never_changes_confidence():
    """higher_timeframe_trend None (veri yok) ya da 'neutral' (ölçümde
    hiç örneklenmemiş kova) iken hiçbir ayarlama yapılmamalı — no-op."""
    agent = TechnicalAgent()
    base_ctx = TechnicalContext(trend="bullish", momentum="strengthening", market_structure="higher_highs_higher_lows")
    baseline = agent.analyze(base_ctx)

    none_case = agent.analyze(base_ctx.model_copy(update={"higher_timeframe_trend": None}))
    neutral_case = agent.analyze(base_ctx.model_copy(update={"higher_timeframe_trend": "neutral"}))

    assert none_case.confidence == baseline.confidence
    assert neutral_case.confidence == baseline.confidence


def test_htf_signal_never_fires_on_wait():
    """direction WAIT iken (score eşiği geçmedi) htf sinyali hiç
    devreye girmemeli — sadece yönlü (LONG/SHORT) çağrılarda anlamlı."""
    agent = TechnicalAgent()
    ctx = TechnicalContext(trend="neutral", higher_timeframe_trend="bullish")
    opinion = agent.analyze(ctx)
    assert opinion.direction == "WAIT"


# --- Faz 468: SESSIZ OLU SINYAL regresyon korumasi ---

def test_market_structure_branches_fire_for_the_producers_actual_output():
    """FAZ 468 — GERÇEK BİR HATA YAKALADI VE BİR DAHA OLMASIN DİYE VAR.

    `technical_agent` yıllardır `context.market_structure == "higher_highs"`
    / `"lower_lows"` karşılaştırması yapıyordu; ama üreticisi
    (`signal_engine._swing_structure()`) "higher_highs_higher_lows" /
    "lower_highs_lower_lows" döndürüyor. İki dal HİÇ eşleşmedi — ajanın
    EN YÜKSEK tekil ağırlığı (1.5) tamamen ölüydü. Canlı veride
    doğrulandı: 3 günde `market_structure` katkısı SIFIR kez üretilmişti.

    Bu, aynı gün içindeki ÜÇÜNCÜ aynı-sınıf hataydı (Faz 453'te
    volume_profile_confirm adapter'dan geçmiyordu). Bu test, üreticinin
    GERÇEKTEN döndürebildiği her değeri ajana verip hiçbirinin sessizce
    yok sayılmadığını doğruluyor — string'i bir tarafta değiştirip
    diğerini unutmak artık test kırar."""
    import inspect

    from market_data.features import signal_engine

    kaynak = inspect.getsource(signal_engine._swing_structure)
    # Ureticinin dondurebilecegi TUM sabit string'ler.
    uretilen = set(re.findall(r'return\s+"([^"]+)"', kaynak))
    assert uretilen, "uretici hic sabit string dondurmuyor -- test guncellenmeli"

    yonlu = {d for d in uretilen if d != "ranging"}
    assert yonlu, "yonlu bir yapi degeri bulunamadi"

    agent = TechnicalAgent()
    for deger in yonlu:
        opinion = agent.analyze(TechnicalContext(market_structure=deger))
        katkilar = opinion.feature_contributions
        assert "market_structure" in katkilar, (
            f'"{deger}" degeri ajanda HIC eslesmiyor -- olu dal. '
            f"Uretici {sorted(uretilen)} donduruyor."
        )
        assert katkilar["market_structure"] != 0.0


def test_market_structure_is_shadowed_not_scored_for_now():
    """Faz 468 — string düzeltildi ama SKORA bağlanmadı: Faz 462'de
    işaretin TERS olduğu ölçüldü (higher_highs_higher_lows P(UP)=0,483
    vs lower_highs_lower_lows 0,590). Eski işaretle skora sokmak, en
    büyük ağırlıkla ters bir sinyal bağlamak olurdu.

    Bu testin kırılması = biri sinyali skora bağladı; o zaman İŞARETİN
    ölçümle uyumlu olduğu ayrıca doğrulanmalı."""
    agent = TechnicalAgent()
    yukselen = agent.analyze(TechnicalContext(market_structure="higher_highs_higher_lows"))
    dusen = agent.analyze(TechnicalContext(market_structure="lower_highs_lower_lows"))

    # Izleniyor...
    assert yukselen.feature_contributions["market_structure"] > 0
    assert dusen.feature_contributions["market_structure"] < 0
    # ...ama TEK BASINA hicbir yon uretmiyor (skora girmiyor).
    assert yukselen.direction == "WAIT"
    assert dusen.direction == "WAIT"


# --- Faz 469: trend'e yapay bag cozuldu ---

def test_momentum_fires_independently_of_trend():
    """FAZ 469 — kullanıcı itirazının doğrudan karşılığı: "gerçekten aynı
    bilgiyse sinyalin KAYNAĞI problemli, yanılarak anlamlı bir sinyali
    kaybedebiliriz."

    Faz 423 momentum'u "trend ile korelasyon 1.000" diye shadow'a almıştı
    — ama korelasyon 1.000 çıkıyordu ÇÜNKÜ koşulun kendisi
    `and context.trend == "bullish"` içeriyordu. Ölçülen redundans,
    sinyalin değil AJANIN KENDİ KODUNUN eseriydi.

    Gerçek veri (trend sabit tutularak, n=29.305) momentum'un bağımsız
    bilgi taşıdığını gösterdi: bearish rejimde weakening 0,6247 vs
    strengthening 0,5736; bullish rejimde 0,5311 vs 0,5095."""
    agent = TechnicalAgent()

    # trend BEARISH iken bile "strengthening" ateslenmeli (eskiden imkansizdi).
    op = agent.analyze(TechnicalContext(trend="bearish", momentum="strengthening"))
    assert op.feature_contributions["momentum"] > 0

    # trend BULLISH iken "weakening" ateslenmeli (eskiden imkansizdi).
    op = agent.analyze(TechnicalContext(trend="bullish", momentum="weakening"))
    assert op.feature_contributions["momentum"] < 0

    # trend YOKKEN de olculebilmeli.
    op = agent.analyze(TechnicalContext(trend="neutral", momentum="strengthening"))
    assert op.feature_contributions["momentum"] > 0


def test_bollinger_and_adx_also_fire_independently_of_trend():
    """momentum ile AYNI kusur bollinger_confirm ve adx_strong_confirm'de
    de vardı — üçü de `and context.trend == ...` ile bağlanmıştı."""
    agent = TechnicalAgent()

    op = agent.analyze(TechnicalContext(trend="bearish", bollinger_percent_b=1.5))
    assert op.feature_contributions["bollinger_confirm"] > 0

    op = agent.analyze(TechnicalContext(
        trend="bearish", adx=30.0, di_plus=30.0, di_minus=10.0,
    ))
    assert op.feature_contributions["adx_strong_confirm"] > 0


def test_ema_alignment_stays_coupled_because_it_is_a_real_subset_of_trend():
    """KASITLI FARK: `ema_alignment` bağı ÇÖZÜLMEDİ, çünkü onunki gerçek
    bir KAYNAK redundansı — `ema20>ema50>ema200` tanımı gereği
    `ema20>ema50` (trend) kümesinin ALT KÜMESİ. Ajan koduyla ilgisi yok,
    dolayısıyla "bağı çözmek" diye bir şey mümkün değil.

    Bu test, ileride biri "tutarlılık olsun" diye onu da değiştirmeye
    kalkarsa gerekçenin kaybolmamasını sağlıyor: ema_alignment
    bullish_aligned iken trend zaten bullish'tir."""
    agent = TechnicalAgent()
    # trend NOTR birakiliyor: ema_alignment'in KENDI katkisini, trend'in
    # skoruyla karistirmadan gormek icin.
    op = agent.analyze(TechnicalContext(ema_alignment="bullish_aligned", trend="neutral"))
    assert op.feature_contributions["ema_alignment"] > 0
    # Shadow'da: TEK BASINA hicbir yon uretmiyor.
    assert op.direction == "WAIT"


def test_decoupling_does_not_change_the_score():
    """Üçü de SHADOW'da kaldığı için üretim davranışı DEĞİŞMEMELİ —
    Faz 464'ün gözlem penceresi açıkken bu kritik."""
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="bullish", momentum="weakening", bollinger_percent_b=1.5,
        adx=30.0, di_plus=30.0, di_minus=10.0, rsi_value=20.0,
    )
    op = agent.analyze(ctx)

    skorlanan = {"trend", "rsi_extreme", "volume_confirmation", "obv_divergence"}
    golge = set(op.feature_contributions) - skorlanan
    assert {"momentum", "bollinger_confirm", "adx_strong_confirm"} <= golge
    # Skor SADECE skorlanan sinyallerden gelmeli.
    implied = sum(v for k, v in op.feature_contributions.items() if k in skorlanan)
    assert abs(abs(implied) - op.confidence * 5.0) < 1e-6
