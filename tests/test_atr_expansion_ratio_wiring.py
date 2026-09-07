"""Faz 437 (2026-09-07) — kullanıcı önceliği ②: ATR ham değeri +
genişleme/daralma oranı zaten hesaplanıyordu (market_data/features/
signal_engine.py) ama hiçbir agent Context'ine ulaşmıyordu. contracts/
technical.py + services/context_adapter.py::to_technical() +
agents/technical_agent.py'ye (SADECE bilgilendirici caveat, skora
girmiyor) kadar izleniyor."""
from contracts.context import CognitiveCycleContext
from contracts.technical import TechnicalContext
from services.context_adapter import ContextAdapter

from agents.technical_agent import TechnicalAgent


def test_to_technical_reads_atr_and_expansion_ratio_from_features():
    ctx = CognitiveCycleContext(
        market={"raw_snapshot": {"atr": 123.45, "atr_expansion_ratio": 2.1}},
    )
    result = ContextAdapter().to_technical(ctx)
    assert result.atr == 123.45
    assert result.atr_expansion_ratio == 2.1


def test_to_technical_defaults_when_atr_fields_are_absent():
    ctx = CognitiveCycleContext(market={"symbol": "NEVERINGESTEDXYZ"})
    result = ContextAdapter().to_technical(ctx)
    assert result.atr == 0.0
    assert result.atr_expansion_ratio is None


def test_technical_agent_adds_a_caveat_for_expanding_volatility_no_score_impact():
    base = dict(trend="bullish", momentum="strengthening", market_structure="higher_highs")
    baseline = TechnicalAgent().analyze(TechnicalContext(**base))
    expanding = TechnicalAgent().analyze(TechnicalContext(**base, atr_expansion_ratio=2.0))

    assert any("ATR genişliyor" in c for c in expanding.caveats)
    assert expanding.confidence == baseline.confidence
    assert expanding.feature_contributions == baseline.feature_contributions


def test_technical_agent_adds_a_caveat_for_contracting_volatility_no_score_impact():
    base = dict(trend="bullish", momentum="strengthening", market_structure="higher_highs")
    baseline = TechnicalAgent().analyze(TechnicalContext(**base))
    contracting = TechnicalAgent().analyze(TechnicalContext(**base, atr_expansion_ratio=0.3))

    assert any("ATR daralıyor" in c for c in contracting.caveats)
    assert contracting.confidence == baseline.confidence
    assert contracting.feature_contributions == baseline.feature_contributions


def test_technical_agent_no_caveat_when_ratio_is_near_1_or_unknown():
    base = dict(trend="bullish", momentum="strengthening", market_structure="higher_highs")
    normal = TechnicalAgent().analyze(TechnicalContext(**base, atr_expansion_ratio=1.0))
    unknown = TechnicalAgent().analyze(TechnicalContext(**base, atr_expansion_ratio=None))

    assert not any("ATR genişliyor" in c or "ATR daralıyor" in c for c in normal.caveats)
    assert not any("ATR genişliyor" in c or "ATR daralıyor" in c for c in unknown.caveats)
