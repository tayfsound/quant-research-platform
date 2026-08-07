"""OnChain Agent testleri."""
from agents.onchain_agent import OnChainAgent
from contracts.onchain import OnChainContext


def test_whale_accumulation_generates_long():
    agent = OnChainAgent()
    ctx = OnChainContext(
        exchange_outflow_24h=500_000_000,
        exchange_inflow_24h=100_000_000,
        whale_accumulation=True,
        stablecoin_mint_24h=200_000_000,
    )
    opinion = agent.analyze(ctx)
    assert opinion.domain.value == "onchain"
    assert opinion.direction == "LONG"
    assert opinion.confidence > 0

def test_whale_distribution_generates_short():
    agent = OnChainAgent()
    ctx = OnChainContext(
        exchange_inflow_24h=500_000_000,
        exchange_outflow_24h=100_000_000,
        whale_distribution=True,
        mvrv_zscore=3.5,
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "SHORT"
    assert opinion.confidence > 0

def test_mvrv_extremes():
    agent = OnChainAgent()
    ctx_low = OnChainContext(mvrv_zscore=-1.5)
    ctx_high = OnChainContext(mvrv_zscore=4.0)

    opinion_low = agent.analyze(ctx_low)
    opinion_high = agent.analyze(ctx_high)

    assert opinion_low.direction == "LONG"
    assert opinion_high.direction == "SHORT"

def test_conflicting_whale_signal_waits():
    agent = OnChainAgent()
    ctx = OnChainContext(
        whale_accumulation=True,
        whale_distribution=True,
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "WAIT"
    assert len(opinion.caveats) > 0
    assert any("Conflicting" in c for c in opinion.caveats)


def test_high_gas_price_adds_caveat_but_does_not_change_direction():
    """Faz 196: gerçek gas price sadece bağlam notu — yönü tek başına
    belirlemiyor (yüksek gas'ın fiyat için bullish mi bearish mi olduğu
    literatürde net değil)."""
    agent = OnChainAgent()
    ctx = OnChainContext(whale_accumulation=True, eth_gas_price_gwei=120.0)
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"  # whale_accumulation'dan geliyor
    assert any("congestion" in c for c in opinion.caveats)


def test_low_gas_price_adds_no_caveat():
    agent = OnChainAgent()
    ctx = OnChainContext(eth_gas_price_gwei=5.0)
    opinion = agent.analyze(ctx)
    assert not any("congestion" in c for c in opinion.caveats)


def test_solana_tps_appears_as_evidence_when_present():
    agent = OnChainAgent()
    ctx = OnChainContext(solana_tps=3500.0)
    opinion = agent.analyze(ctx)
    assert any("Solana" in e for e in opinion.evidence)


def test_no_onchain_network_signals_means_no_extra_evidence_or_caveat():
    agent = OnChainAgent()
    ctx = OnChainContext()
    opinion = agent.analyze(ctx)
    assert not any("Solana" in e for e in opinion.evidence)
    assert not any("congestion" in c for c in opinion.caveats)


def test_single_real_network_trend_signal_alone_produces_a_direction():
    """Faz 247: kritik bulgu — exchange_inflow/outflow, whale_accumulation/
    distribution, mvrv_zscore hâlâ hiç uygulanmadı (Faz 196/215'in kasıtlı
    kararı, gerçek veride hep varsayılan/nötr). Gerçekten çalışan tek
    sinyallerden biri (network_activity_trend) TEK BAŞINA (±0.5) eski
    eşiği (>0.5) hiçbir zaman aşamıyordu — ajan elindeki gerçek bilgiyi
    hiç ifade edemiyordu. Bu test, eşik düzeltmesinden sonra tek bir
    gerçek trend sinyalinin artık (düşük konviksiyonla da olsa) bir görüş
    üretebildiğini kanıtlıyor."""
    agent = OnChainAgent()
    ctx = OnChainContext(symbol="BTCUSDT", network_activity_trend="rising")
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"
    assert 0 < opinion.confidence < 0.2

    ctx_falling = OnChainContext(symbol="BTCUSDT", hash_rate_trend="falling")
    opinion_falling = agent.analyze(ctx_falling)
    assert opinion_falling.direction == "SHORT"


def test_btc_trend_signal_does_not_affect_direction_for_other_symbols():
    """Faz 248: kritik bulgu — network_activity_trend/hash_rate_trend
    SADECE Bitcoin zincirinden geliyor ama önceden TÜM sembollere
    (ETHUSDT dahil) aynen uygulanıyordu. Bu test, aynı "rising" sinyalinin
    ETHUSDT için yön puanına KATILMADIĞINI (WAIT kaldığını) ama bilgi notu
    olarak hâlâ göründüğünü kanıtlıyor."""
    agent = OnChainAgent()
    ctx = OnChainContext(symbol="ETHUSDT", network_activity_trend="rising")
    opinion = agent.analyze(ctx)
    assert opinion.direction == "WAIT"
    assert any("bilgi amaçlı" in c for c in opinion.caveats)
