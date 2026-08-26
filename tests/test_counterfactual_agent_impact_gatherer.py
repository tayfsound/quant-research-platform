"""Faz 363 — services/counterfactual_agent_impact_gatherer.py. Ağır
DB/risk-motoru/ağ zincirinin tamamı manuel olarak gerçek üretim
verisiyle uçtan uca doğrulandı (BTCUSDT flip vakası: risk kapıları/
DecisionFusion EV kapısı doğru çalıştı). Burada SADECE ucuz, hızlı,
deterministik dalları kilitliyoruz — ağır dalın tamamını mock'lamak
(RiskEngine+RiskTargetStage+DecisionFusion+RiskGateStage+Binance) bu
noktada orantısız bir efor olurdu."""
from datetime import UTC, datetime

from contracts.agent import AgentDomain, AgentOpinion
from services.counterfactual_agent_impact_gatherer import replay_flipped_decision, _load_breakeven_settings


def _opinion_dict(domain: AgentDomain, direction: str, confidence: float) -> dict:
    o = AgentOpinion(domain=domain, direction=direction, confidence=confidence)
    o.recalculate()
    return o.model_dump(mode="json")


def test_replay_flipped_decision_returns_none_when_not_pivotal():
    """excluded_domain'i çıkarmak yön değiştirmiyorsa (not_pivotal) replay
    edilecek FARKLI bir işlem yok -- None dönmeli, zorla bir sonuç
    üretilmemeli."""
    decision_row = {
        "agent_contributions": [
            _opinion_dict(AgentDomain.TECHNICAL, "LONG", 0.9),
            _opinion_dict(AgentDomain.MACRO, "LONG", 0.9),
        ],
        "direction": "LONG",
        "entry_price": 100.0,
        "symbol": "BTCUSDT",
        "opened_at": datetime.now(UTC),
        "quantity": 0.1,
    }
    settings = _load_breakeven_settings()
    result = replay_flipped_decision(decision_row, "technical", settings)
    assert result is None


def test_replay_flipped_decision_returns_none_when_caused_trade():
    """Karşı-olgusal WAIT'e düşerse (caused_trade) replay edilecek YÖNLÜ
    bir işlem yok -- None dönmeli."""
    decision_row = {
        "agent_contributions": [
            _opinion_dict(AgentDomain.TECHNICAL, "LONG", 0.9),
            _opinion_dict(AgentDomain.TIME, "WAIT", 0.5),
        ],
        "direction": "LONG",
        "entry_price": 100.0,
        "symbol": "BTCUSDT",
        "opened_at": datetime.now(UTC),
        "quantity": 0.1,
    }
    settings = _load_breakeven_settings()
    result = replay_flipped_decision(decision_row, "technical", settings)
    assert result is None


def test_replay_flipped_decision_returns_none_when_domain_never_voted():
    decision_row = {
        "agent_contributions": [_opinion_dict(AgentDomain.TECHNICAL, "LONG", 0.9)],
        "direction": "LONG",
        "entry_price": 100.0,
        "symbol": "BTCUSDT",
        "opened_at": datetime.now(UTC),
        "quantity": 0.1,
    }
    settings = _load_breakeven_settings()
    result = replay_flipped_decision(decision_row, "quant", settings)
    assert result is None


def test_replay_flipped_decision_handles_missing_market_snapshot_honestly():
    """Faz 363 — çok eski bir kayıtta market_snapshot hiç yoksa (RiskTarget
    Stage'in ATR/fiyat girdisi yok) icat edilmiş bir sonuç üretilmez,
    dürüstçe 'yetersiz saklı bağlam' döner."""
    contributions = [
        _opinion_dict(AgentDomain.TECHNICAL, "LONG", 0.95),
        _opinion_dict(AgentDomain.MACRO, "SHORT", 0.6),
    ]
    decision_row = {
        "agent_contributions": contributions,
        "direction": "LONG",
        "entry_price": 100.0,
        "symbol": "BTCUSDT",
        "opened_at": datetime.now(UTC),
        "quantity": 0.1,
    }
    settings = _load_breakeven_settings()
    result = replay_flipped_decision(decision_row, "technical", settings)
    assert result["would_have_traded"] is False
    assert result["rejection_reason"] == "insufficient_stored_context"
    assert result["counterfactual_direction"] == "SHORT"
