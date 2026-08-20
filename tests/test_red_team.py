"""Adversarial Red-Team modu testleri.

NOT: transformers.* KASITLI OLARAK mock'lanmıyor — backtest/red_team.py'nin
kendi modül docstring'indeki güvenlik notuna bkz: ctx.market.features
doldurulunca MemoryStage gerçek embedding modelini (sentence-transformers,
yerel önbellekli) tetikliyor, standart mock deseniyle çalışmıyor (aynı,
tests/test_real_historical_backtest.py'nin izlediği desen).

Faz 268-sonrası — kritik bulgu: R/R oranı gerçek OOS doğrulamasıyla
1:4'ten ~1:0.56'ya çekilince (bkz. engines/cognitive_pipeline.py::
RiskTargetStage), DecisionFusion'ın EV kapısının breakeven eşiği ~%20'den
~%64'e çıktı. whipsaw_chop(period_bars=4)'ün ürettiği raw confidence çoğu
barda bunu geçmiyordu (trades_taken=0 — kill switch hiç tetiklenemiyordu,
çünkü hiç işlem açılmıyordu). period_bars=15 daha güçlü/net bir salınım
üretip raw confidence'ı tutarlı biçimde ~%66'ya çıkarıyor (ölçüldü).
calibrate_confidence de ayrıca uygulanıyor ama paylaşılan test DB'sinin
biriken (ve düzensiz/az örneklemli) kalibrasyon eğrisine bağımlı olmasın
diye burada identity'ye (kimlik fonksiyonu) sabitleniyor — bu testlerin
asıl amacı kalibrasyon eğrisini değil kill switch/drawdown mekanizmasını
doğrulamak."""
from unittest.mock import patch

import pytest

from backtest.red_team import (
    correlated_multi_asset_crash,
    flash_crash_and_recover,
    run_red_team_scenario,
    whipsaw_chop,
)
from services.cognitive_engine import CognitiveEngine


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    # Faz 268-sonrası — kritik bulgu: SourceReliabilityAgent artık GERÇEK,
    # kalıcı AgentMemory geçmişinden reliability hesaplıyor (bkz. agents/
    # source_reliability_agent.py). Varsayılan AgentMemory() TÜM test
    # sürecinin paylaştığı tek bir dosyaya yazıyor (conftest.py::
    # AGENT_MEMORY_STORAGE_PATH) — bu dosyaya başka test dosyalarının
    # yazdığı "technical" kayıtları (ör. test_agent_auto_bench.py'nin
    # bilerek yazdığı was_correct=False kayıtlar) buradaki senaryoyu
    # kirletmesin diye izole bir AgentMemory veriliyor.
    #
    # İkinci, daha ince bulgu: bu senaryo SADECE technical'in gerçek,
    # fiyat-türevli sinyaline dayanıyor (whipsaw_chop) — ama _build_
    # backtest_context() macro/sentiment/onchain/vb. için hiç gerçek veri
    # sağlamıyor (backtest/real_historical_backtest.py, sadece technical+
    # quant+pattern hesaplıyor). ContextAdapter bu domain'ler için
    # Pydantic VARSAYILAN değerleriyle bir context üretiyor — ör. macro
    # her zaman AYNI (sabit, fiyattan bağımsız) "LONG, liquidity
    # expansionary" oyu veriyor. Eski (bozuk, confidence-tabanlı) mekanizma
    # bunları YANLIŞ sebeple ama tesadüfen susturuyordu (düşük raporlanan
    # confidence → "güvenilmez"). Doğru mekanizma (gerçek isabet oranı)
    # haklı olarak susturmuyor — kanıt yok. Sonuç: sabit macro oyu,
    # technical'in dönüşümlü sinyaliyle sürekli çekişip belief.strength'i
    # asla eşiğin üstüne çıkarmıyor, senaryo SONSUZA DEK WAIT'te kalıyor
    # (gerçek 150 bar'lık izlemeyle doğrulandı). Bu senaryonun placeholder
    # domain'lerinin gerçek bir sinyali OLMADIĞINI dürüstçe belirtmek için
    # (icat edilmiş bir "iyi" geçmiş değil, "bu bağlamda hiç kanıtlanmamış"
    # gerçeği), technical/epistemology HARİÇ tüm domain'ler için GERÇEK
    # (ama olumsuz) bir geçmiş seed ediliyor — tam olarak eski mekanizmanın
    # kazara ürettiği sonucu, artık doğru/açık bir sebeple.
    from contracts.agent_performance import AgentPerformanceRecord
    from services.agent_memory import AgentMemory

    eng = CognitiveEngine()
    isolated_memory = AgentMemory(storage_path=str(tmp_path_factory.mktemp("red_team_agent_memory")))
    placeholder_domains = (
        "macro", "sentiment", "onchain", "pattern", "quant",
        "order_flow", "time", "relative_strength",
    )
    for domain in placeholder_domains:
        for _ in range(12):
            isolated_memory.record(AgentPerformanceRecord(
                agent_domain=domain, direction="LONG", confidence=0.5, was_correct=False,
            ))
    eng.council_stage.orchestrator.reliability_annotator.agent.memory = isolated_memory
    return eng


def test_severe_whipsaw_eventually_trips_the_kill_switch(engine):
    """Gerçek olayla (2026-08-12, gecikmeli trend rejiminin aktif bir
    tersine dönüşü okuyamayıp 50 ardışık gerçek kayba yol açması) AYNI
    mekanizmayı sentetik olarak üretip, kill switch'in GERÇEKTEN
    devreye girdiğini doğrular."""
    bars = whipsaw_chop(n_bars=150, period_bars=15, amplitude_pct=0.06)
    with patch("services.decision_fusion.calibrate_confidence", side_effect=lambda x, curve=None: x):
        result = run_red_team_scenario(
            bars, scenario_name="whipsaw", kill_switch_consecutive_losses=4,
            max_drawdown_limit_pct=0.9, engine=engine,
        )
    assert result.kill_switch_tripped is True
    assert result.kill_switch_tripped_at_bar is not None
    assert result.max_consecutive_losses >= 4


def test_kill_switch_disabled_means_losses_keep_accumulating(engine):
    """kill_switch_consecutive_losses=0 (devre dışı) — RiskEngine'in kendi
    kuralı gereği (bkz. engines/risk_engine.py) hiçbir eşik aşılmışlık
    kontrolü yapılmaz, AYNI kötü senaryoda kayıplar sınırsız birikir.
    Kill switch'in GERÇEKTEN bir şey değiştirdiğini (aksi halde ne işe
    yaradığı belirsiz kalırdı) kanıtlayan karşılaştırma testi."""
    bars = whipsaw_chop(n_bars=150, period_bars=15, amplitude_pct=0.06)
    with patch("services.decision_fusion.calibrate_confidence", side_effect=lambda x, curve=None: x):
        disabled = run_red_team_scenario(
            bars, scenario_name="whipsaw_disabled", kill_switch_consecutive_losses=0,
            max_drawdown_limit_pct=0.9, engine=engine,
        )
        enabled = run_red_team_scenario(
            bars, scenario_name="whipsaw_enabled", kill_switch_consecutive_losses=4,
            max_drawdown_limit_pct=0.9, engine=engine,
        )
    assert disabled.kill_switch_tripped is False
    assert enabled.kill_switch_tripped is True
    # Aynı deterministik fiyat serisi, kill switch tetiklendiği ana kadar
    # AYNI kararları üretiyor — o ana kadarki drawdown ("enabled") o yüzden
    # "disabled"ın NİHAİ drawdown'ından (tüm seriyi görmüş) asla daha kötü
    # olamaz; kill switch sonrası piyasa toparlanırsa eşit de olabilir
    # (gerçekten gözlemlendi) — asla daha kötü olmaması garanti, "daha iyi"
    # garanti değil.
    assert enabled.max_drawdown_pct <= disabled.max_drawdown_pct


def test_tight_max_drawdown_limit_caps_losses_even_without_kill_switch(engine):
    """MAX_DRAWDOWN limiti (engines/risk_engine.py'nin ayrı bir kontrolü)
    kill switch tamamen kapalıyken bile kendi başına bağımsız bir sermaye
    koruması sağlamalı — tek bir savunma hattına bağımlı kalınmadığını
    doğrular."""
    bars = whipsaw_chop(n_bars=150, period_bars=4, amplitude_pct=0.06)
    result = run_red_team_scenario(
        bars, scenario_name="tight_drawdown", kill_switch_consecutive_losses=0,
        max_drawdown_limit_pct=0.05, engine=engine,
    )
    # %5 limit + üstteyken hâlâ açık kalan tek bir işlemin payı — sıkı
    # ama makul bir tavan, sınırsız birikimin (yukarıdaki test ~%34)
    # çok altında kalmalı.
    assert result.max_drawdown_pct < 0.10


def test_flash_crash_and_recover_generates_a_severe_synthetic_drop():
    bars = flash_crash_and_recover(base_price=100.0, n_bars=100, crash_at_bar=40, crash_depth_pct=0.35)
    closes = [b.close for b in bars]
    assert min(closes) < 100.0 * 0.68
    assert closes[0] == 100.0


def test_correlated_multi_asset_crash_produces_a_shared_crash_across_symbols():
    data = correlated_multi_asset_crash(["BTCUSDT", "ETHUSDT", "SOLUSDT"], n_bars=100, crash_at_bar=40)
    assert set(data.keys()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
    for symbol, bars in data.items():
        closes = [b.close for b in bars]
        assert min(closes) < max(closes) * 0.85, f"{symbol} sert bir çöküş yaşamadı"


def test_benign_steady_uptrend_does_not_trip_the_kill_switch(engine):
    """Kill switch'in yanlış-pozitif üretmediğini (sağlıklı, tutarlı bir
    trend'de tetiklenmediğini) doğrulayan negatif kontrol."""
    from datetime import UTC, datetime, timedelta

    from market_data.ingestion.ohlcv import OHLCV

    now = datetime.now(UTC)
    price = 100.0
    bars = []
    for i in range(150):
        price *= 1.004  # istikrarlı, düşük gürültülü yükseliş
        bars.append(OHLCV(
            timestamp=now + timedelta(minutes=i), open=price,
            high=price * 1.001, low=price * 0.999, close=price, volume=100.0,
        ))
    result = run_red_team_scenario(
        bars, scenario_name="steady_uptrend", kill_switch_consecutive_losses=4,
        max_drawdown_limit_pct=0.9, engine=engine,
    )
    assert result.kill_switch_tripped is False
