"""Faz 239-241: Online Meta-Learning (CMA-ES ajan katsayı optimizasyonu).
meta_optimizer/agent_tuner.py'nin matematiğini test ediyor — gerçek DB'ye
karşı sadece load_historical_technical_records (kelly_sizing testlerinin
deseniyle aynı: DECISIONTEST{uuid} sembolüyle gerçek satır ekleyip
gerçekten geri okunabildiğini doğruluyor), geri kalanı deterministik
sentetik veriyle (CMA-ES'in kendisi gerçek/sentetik ayrımı yapmıyor —
sadece TechnicalAgent.analyze() + gerçek pnl sayıları)."""
from datetime import UTC, datetime
from uuid import uuid4

import numpy as np

from agents.technical_agent import TechnicalAgent, TechnicalAgentCoefficients
from contracts.decision_event import DecisionEvent
from contracts.technical import TechnicalContext
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from meta_optimizer.agent_tuner import (
    HistoricalTechnicalRecord,
    clip_vector,
    load_historical_technical_records,
    optimize_technical_agent_coefficients,
    sharpe_like,
    synthetic_pnls,
    walk_forward_validate,
)


def _bullish_context() -> TechnicalContext:
    return TechnicalContext(trend="bullish", market_structure="higher_highs_higher_lows")


def _bearish_context() -> TechnicalContext:
    return TechnicalContext(trend="bearish", market_structure="lower_highs_lower_lows")


def test_sharpe_like_matches_hand_computed_mean_over_std():
    pnls = np.array([10.0, -5.0, 10.0, -5.0])
    result = sharpe_like(pnls)
    expected = float(np.mean(pnls) / np.std(pnls))
    assert abs(result - expected) < 1e-9


def test_sharpe_like_is_zero_for_empty_or_zero_variance_series():
    assert sharpe_like(np.array([])) == 0.0
    assert sharpe_like(np.array([5.0])) == 0.0  # tek örneklem -> std=0
    assert sharpe_like(np.array([3.0, 3.0, 3.0])) == 0.0  # sabit seri -> std=0


def test_synthetic_returns_use_forward_price_not_trade_pnl():
    """FAZ 466 — HEDEF DEĞİŞTİ. Eskiden ajanın oyu YÜRÜTÜLEN yönle
    aynıysa gerçek `pnl`, tersse `-pnl` kullanılıyordu. İki kusuru vardı:
    (a) `pnl` bir TRADE sonucu -- bariyer/stop/tutma süresine bağlı, oysa
    ölçmek istediğimiz YÖN; (b) `-pnl`, "ters bahis tam simetrik sonuç
    verirdi" varsayıyordu, ki bariyerler asimetrik olduğu için yanlış.

    Artık sabit ufuklu GERÇEK ileri getiri kullanılıyor: LONG oyunda
    +getiri, SHORT oyunda −getiri. Burada `pnl` KASITLI olarak yanıltıcı
    seçildi (−999) -- sonuca hiç girmemeli."""
    default = TechnicalAgentCoefficients()
    records = [
        HistoricalTechnicalRecord(_bullish_context(), "LONG", -999.0, forward_return=0.02),
    ]
    assert synthetic_pnls(default, records).tolist() == [0.02]


def test_synthetic_returns_negate_forward_return_for_short_votes():
    default = TechnicalAgentCoefficients()
    records = [
        HistoricalTechnicalRecord(_bearish_context(), "LONG", -999.0, forward_return=0.02),
    ]
    assert synthetic_pnls(default, records).tolist() == [-0.02]


def test_records_without_forward_return_contribute_nothing():
    """Fail-closed: ileri fiyat bulunamadıysa uydurma bir getiri
    üretilmez."""
    default = TechnicalAgentCoefficients()
    records = [HistoricalTechnicalRecord(_bullish_context(), "LONG", 42.0)]
    assert synthetic_pnls(default, records).tolist() == [0.0]


def test_has_forward_returns_detects_a_fully_empty_target():
    """Faz 466 — yön-tabanlı hedef, forward_return olmadan SESSİZCE her θ
    için sıfır dizisi üretir ve CMA-ES "hiçbir şey fark etmiyor" sonucuna
    varır; bu, kullanıcının şikâyet ettiği "hep sıfır" durumunun yeni bir
    kılıkta tekrarı olurdu."""
    from meta_optimizer.agent_tuner import has_forward_returns

    assert has_forward_returns([
        HistoricalTechnicalRecord(_bullish_context(), "LONG", 1.0),
    ]) is False
    assert has_forward_returns([
        HistoricalTechnicalRecord(_bullish_context(), "LONG", 1.0, forward_return=0.01),
    ]) is True


def test_synthetic_pnls_is_zero_when_agent_waits():
    default = TechnicalAgentCoefficients()
    neutral_ctx = TechnicalContext()  # her şey "neutral" -> WAIT
    records = [HistoricalTechnicalRecord(neutral_ctx, "LONG", 42.0, forward_return=0.02)]
    pnls = synthetic_pnls(default, records)
    assert pnls.tolist() == [0.0]


def test_clip_vector_clamps_each_field_to_its_own_bound():
    names = TechnicalAgentCoefficients.field_names()
    # hepsini aşırı büyük bir değere ayarla -> her biri kendi üst sınırına düşmeli
    oversized = [100.0] * len(names)
    clipped = clip_vector(oversized)
    coeffs = TechnicalAgentCoefficients.from_vector(clipped)
    assert coeffs.adx_weak_discount == 1.0  # kendi üst sınırı [0,1]
    assert coeffs.confidence_divisor == 10.0  # kendi üst sınırı [2,10]
    assert coeffs.trend_weight == 2.0  # yon tasiyan katsayilarin ust siniri

    undersized = [-100.0] * len(names)
    clipped_low = clip_vector(undersized)
    coeffs_low = TechnicalAgentCoefficients.from_vector(clipped_low)
    # FAZ 466: yon tasiyan katsayilar artik NEGATIF olabiliyor. Faz 239
    # bunu "icat edilmis davranis" diye yasaklamisti; Faz 460/463 gercek
    # veriyle (n=132.144, gunluk tutarlilik + sembol-ici dogrulama) tam
    # tersini olctu -- trend/momentum/ema_alignment/adx/bollinger bu
    # piyasada TERS calisiyor. Negatife izin vermemek, arama uzayindan
    # DOGRU COZUMU disliyordu.
    assert coeffs_low.trend_weight == -2.0
    assert coeffs_low.adx_weak_discount == 0.0   # carpimsal indirim, [0,1] disi anlamsiz
    assert coeffs_low.confidence_divisor == 2.0  # pozitif olmak ZORUNDA


def test_optimize_technical_agent_coefficients_beats_a_deliberately_bad_baseline():
    """Gerçek council olmadan CMA-ES'in temel matematiğini kanıtlıyor:
    trend her zaman GERÇEK yürütülen yönle uyumlu (ideal, gürültüsüz bir
    sentetik veri seti) verildiğinde, optimize edilmiş θ'nın sentetik
    Sharpe'ı, trend_weight'i KASITLI OLARAK SIFIRLANMIŞ (bu sinyali
    tamamen görmezden gelen) bir taban çizgiden kesinlikle daha iyi
    olmalı."""
    rng = np.random.default_rng(7)
    records = []
    for _ in range(60):
        bullish = rng.random() > 0.5
        ctx = _bullish_context() if bullish else _bearish_context()
        executed = "LONG" if bullish else "SHORT"
        pnl = float(rng.uniform(5.0, 20.0))
        # Faz 466: hedef artik ileri getiri -- bullish baglamda fiyat
        # GERCEKTEN yukselmis, bearish'te dusmus (ideal, gurultusuz set).
        forward = float(rng.uniform(0.005, 0.02)) * (1 if bullish else -1)
        records.append(HistoricalTechnicalRecord(ctx, executed, pnl, forward))

    blind_baseline = TechnicalAgentCoefficients(
        trend_weight=0.0, momentum_weight=0.0, market_structure_weight=0.0,
        ema_alignment_weight=0.0, rsi_extreme_weight=0.0,
    )
    baseline_sharpe = sharpe_like(synthetic_pnls(blind_baseline, records))

    tuned_coeffs, tuned_sharpe = optimize_technical_agent_coefficients(
        records, max_iterations=40, seed=1,
    )

    assert tuned_sharpe > baseline_sharpe
    # Optimizasyon trend/market_structure sinyalini keşfetmiş olmalı —
    # rastgele/sıfıra yakın değil, gerçekten pozitif bir ağırlık.
    assert tuned_coeffs.trend_weight > 0.1 or tuned_coeffs.market_structure_weight > 0.1


def test_walk_forward_validate_returns_empty_result_when_not_enough_records():
    result = walk_forward_validate([], train_size=400, test_size=100, step=100)
    assert result["folds"] == []
    assert result["mean_oos_sharpe_tuned"] is None
    assert result["sample_count"] == 0


def test_walk_forward_validate_produces_out_of_sample_folds_with_both_sharpes():
    rng = np.random.default_rng(3)
    records = []
    for _ in range(260):
        bullish = rng.random() > 0.5
        ctx = _bullish_context() if bullish else _bearish_context()
        executed = "LONG" if bullish else "SHORT"
        pnl = float(rng.uniform(5.0, 20.0))
        records.append(HistoricalTechnicalRecord(ctx, executed, pnl))

    result = walk_forward_validate(
        records, train_size=100, test_size=50, step=50, embargo=5, max_iterations=15,
    )

    assert len(result["folds"]) >= 1
    for fold in result["folds"]:
        assert isinstance(fold["tuned_coefficients"], TechnicalAgentCoefficients)
        assert isinstance(fold["oos_sharpe_tuned"], float)
        assert isinstance(fold["oos_sharpe_baseline"], float)
    assert result["sample_count"] == len(records)
    assert result["sharpe_improvement"] == (
        result["mean_oos_sharpe_tuned"] - result["mean_oos_sharpe_baseline"]
    )


def test_load_historical_technical_records_reflects_real_closed_decisions():
    """Gerçek DB'ye karşı: agent_contributions içinde hem bir market_snapshot
    (gerçek TechnicalContext feature'ları) hem de technical domain'inin
    gerçek oyu olan kapanmış bir karar, load_historical_technical_records
    tarafından doğru şekilde geri okunabilmeli."""
    symbol = f"AGENTTUNER{uuid4().hex[:6]}"
    now = datetime.now(UTC)

    event = DecisionEvent(
        id=uuid4(),
        symbol=symbol,
        proposed_direction="LONG",
        final_action="LONG",
        final_size=1.0,
        confidence=0.7,
        status="open",
        entry_price=100.0,
        quantity=1.0,
        agent_opinions=[
            {"domain": "technical", "direction": "LONG", "confidence": 0.7, "evidence": [], "caveats": []},
        ],
        market_snapshot={
            "features": {
                "trend": "bullish",
                "market_structure": "higher_highs",
                "RSI": 28.0,
                "adx": 30.0,
            },
        },
    )
    with SessionFactory.get_session() as session:
        repo = DecisionPersistor(session)
        repo.persist(event)
        repo.close_position(decision_id=str(event.id), exit_price=110.0, pnl=15.0, closed_at=now)

    records = load_historical_technical_records(window=5000)
    matching = [
        r for r in records
        if r.executed_direction == "LONG" and abs(r.pnl - 15.0) < 1e-6
        and r.context.trend == "bullish" and r.context.rsi_value == 28.0
    ]
    assert len(matching) >= 1


def test_load_historical_technical_records_returns_most_recent_window_not_oldest():
    """2026-09-03 — kullanıcı bulgusu: "Meta-Learning Effectiveness
    haftalardır boş." Kök neden: eski kod `ORDER BY closed_at ASC LIMIT
    :window` kullanıyordu — toplam uygun kayıt `window`'u geçtiği andan
    itibaren bu HER ZAMAN aynı en eski satırları döner, tablo büyüdükçe
    asla ilerlemezdi (6824 kayıt varken pencere hâlâ 2026-08-11..08-24
    arasında donmuştu). Bu test bir kaydı GERÇEKTEN eski (2000-01-01),
    bir kaydı GERÇEKTEN yeni (şimdi) closed_at ile kapatıp window=1
    isteyince SADECE yeni kaydın döndüğünü doğruluyor — eski kod bu
    testte eski kaydı (veya ikisini de, DB'deki ilk 1 satıra göre)
    döndürürdü."""
    now = datetime.now(UTC)
    ancient = datetime(2000, 1, 1, tzinfo=UTC)

    def _make_event(symbol: str) -> DecisionEvent:
        return DecisionEvent(
            id=uuid4(),
            symbol=symbol,
            proposed_direction="LONG",
            final_action="LONG",
            final_size=1.0,
            confidence=0.7,
            status="open",
            entry_price=100.0,
            quantity=1.0,
            agent_opinions=[
                {"domain": "technical", "direction": "LONG", "confidence": 0.7, "evidence": [], "caveats": []},
            ],
            market_snapshot={"features": {"trend": "bullish", "market_structure": "higher_highs"}},
        )

    ancient_symbol = f"ATOLD{uuid4().hex[:6]}"
    recent_symbol = f"ATNEW{uuid4().hex[:6]}"
    with SessionFactory.get_session() as session:
        repo = DecisionPersistor(session)
        ancient_event = _make_event(ancient_symbol)
        repo.persist(ancient_event)
        repo.close_position(decision_id=str(ancient_event.id), exit_price=110.0, pnl=1.0, closed_at=ancient)

        recent_event = _make_event(recent_symbol)
        repo.persist(recent_event)
        repo.close_position(decision_id=str(recent_event.id), exit_price=110.0, pnl=2.0, closed_at=now)

    records = load_historical_technical_records(window=1)
    assert len(records) == 1
    assert abs(records[0].pnl - 2.0) < 1e-6


def test_technical_agent_with_tuned_coefficients_is_independent_of_default_instance():
    """agents/technical_agent.py refactor'unun gerçek davranış-koruma
    kanıtı: coefficients=None (varsayılan) hâlâ eski sabit-katsayılı
    davranışla birebir aynı, coefficients verildiğinde İSE gerçekten
    farklı bir skor/yön üretebiliyor."""
    ctx = TechnicalContext(trend="bullish")  # tek başına score=1.0 (WAIT eşiğinin altında, 0.5'i geçmiyor... trend_weight=1.0 > 0.5 -> LONG)

    default_agent = TechnicalAgent()
    zero_trend_agent = TechnicalAgent(
        coefficients=TechnicalAgentCoefficients(trend_weight=0.0),
    )

    default_opinion = default_agent.analyze(ctx)
    zeroed_opinion = zero_trend_agent.analyze(ctx)

    assert default_opinion.direction == "LONG"
    assert zeroed_opinion.direction == "WAIT"


def test_optimizer_can_now_discover_an_inverted_signal():
    """FAZ 466'NIN ASIL AMACI. Bu test, düzeltmeden ÖNCE geçmesi
    İMKÂNSIZDI: `FIELD_BOUNDS` tüm ağırlıkları `(0.0, 2.0)`'a
    hapsettiği için CMA-ES bir sinyali sıfıra indirebiliyor ama
    İŞARETİNİ ÇEVİREMİYORDU.

    Kullanıcının şikâyeti tam olarak bunun sonucuydu: "meta learning hâlâ
    çalışmıyor, hep sıfır, kurduğumuzdan beri bir tur bile gerçekleşmedi."
    Optimizasyon çalışıyordu ama ulaşabildiği en iyi nokta "tüm sinyalleri
    sustur" idi, o da bir iyileşme sayılmıyordu (son deneme 2026-09-03:
    sharpe_improvement −0,017, gereken +0,4).

    Buradaki sentetik veri, Faz 460/463'te GERÇEK veride ölçülen durumun
    birebir taklidi: bullish bağlamda fiyat DÜŞÜYOR. Doğru çözüm negatif
    bir trend_weight ve optimizasyon artık ona ULAŞABİLMELİ."""
    rng = np.random.default_rng(11)
    records = []
    for _ in range(80):
        bullish = rng.random() > 0.5
        ctx = _bullish_context() if bullish else _bearish_context()
        # TERS piyasa: bullish sinyal -> fiyat DUSUYOR.
        forward = float(rng.uniform(0.005, 0.02)) * (-1 if bullish else 1)
        records.append(HistoricalTechnicalRecord(ctx, "LONG", 1.0, forward))

    tuned_coeffs, tuned_sharpe = optimize_technical_agent_coefficients(
        records, max_iterations=60, seed=3,
    )

    # Varsayilan (pozitif isaretli) katsayilar bu piyasada ZARAR ediyor.
    default_sharpe = sharpe_like(synthetic_pnls(TechnicalAgentCoefficients(), records))
    assert default_sharpe < 0

    # Optimizasyon ters isareti KESFETMIS olmali.
    assert tuned_sharpe > default_sharpe
    yon_tasiyanlar = [
        tuned_coeffs.trend_weight, tuned_coeffs.momentum_weight,
        tuned_coeffs.market_structure_weight, tuned_coeffs.ema_alignment_weight,
    ]
    assert any(w < -0.1 for w in yon_tasiyanlar), (
        f"Hicbir katsayi negatife gecmedi: {yon_tasiyanlar}"
    )
