"""Faz 394 — engines/cognitive_pipeline.py::HistoricalAnalogOverrideStage.
Kullanıcı isteği ("tam mimari değişim"): gate_eligible bir Historical
Analog eşleştiğinde belief.strength'in cluster/crowding/coverage
skorlaması YERİNE gerçek ampirik win_rate ile override edilmesi.
tests/test_knowledge_stage_cross_asset_context.py'deki AYNI desen
(gerçek DB'ye rapor kaydet, stage'i çalıştır, doğru davranışı doğrula)."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.historical_analog_report import HistoricalAnalogReport
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.historical_analog_report_repository import (
    HistoricalAnalogReportRepository,
)
from database.session_factory import SessionFactory
from engines.cognitive_pipeline import HistoricalAnalogOverrideStage

_GATE_ELIGIBLE_ANALOG = {
    "domains": ["sentiment", "technical"], "market_regime": "bullish_normal", "direction": "LONG",
    "combination_size": 2, "sample_size": 102, "effective_sample_size": 26.0,
    "win_rate": 0.951, "win_rate_delta_vs_baseline": 0.25, "fdr_significant": True,
    "oos_survival": True, "gate_eligible": True,
}


def _reset_defaults() -> None:
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("historical_analog_override_enabled", "false", updated_by="test")


def _enable_override() -> None:
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("historical_analog_override_enabled", "true", updated_by="test")


def _save_report(analogs: list[dict]) -> None:
    with SessionFactory.get_session() as session:
        HistoricalAnalogReportRepository(session).save(
            HistoricalAnalogReport(
                result={"analogs": analogs, "baseline_win_rate": 0.7, "baseline_sample_size": 1831, "n_trades": 1831}
            )
        )


def _ctx(trend: str = "bullish", volatility_regime: str = "normal") -> CognitiveCycleContext:
    ctx = CognitiveCycleContext()
    ctx.market.symbol = "SOLUSDT"
    ctx.market.features = {"trend": trend, "volatility_regime": volatility_regime}
    return ctx


def _opinions(domains: list[AgentDomain], direction: str) -> list[AgentOpinion]:
    result = []
    for d in domains:
        o = AgentOpinion(domain=d, direction=direction, confidence=0.8)
        o.recalculate()
        result.append(o)
    return result


def test_disabled_by_default_leaves_belief_unchanged():
    _reset_defaults()
    _save_report([_GATE_ELIGIBLE_ANALOG])
    belief = Belief(direction="LONG", strength=0.3521)
    opinions = _opinions([AgentDomain.SENTIMENT, AgentDomain.TECHNICAL], "LONG")

    result = HistoricalAnalogOverrideStage().execute(_ctx(), belief, opinions)

    assert result.strength == 0.3521
    assert result is belief


def test_enabled_and_matching_overrides_strength_to_empirical_win_rate():
    _reset_defaults()
    _enable_override()
    _save_report([_GATE_ELIGIBLE_ANALOG])
    try:
        belief = Belief(direction="LONG", strength=0.3521)
        opinions = _opinions([AgentDomain.SENTIMENT, AgentDomain.TECHNICAL], "LONG")

        result = HistoricalAnalogOverrideStage().execute(_ctx(), belief, opinions)

        assert result.strength == 0.951
        assert result.direction == "LONG"
    finally:
        _reset_defaults()


def test_enabled_but_not_gate_eligible_leaves_belief_unchanged():
    _reset_defaults()
    _enable_override()
    not_eligible = {**_GATE_ELIGIBLE_ANALOG, "gate_eligible": False}
    _save_report([not_eligible])
    try:
        belief = Belief(direction="LONG", strength=0.3521)
        opinions = _opinions([AgentDomain.SENTIMENT, AgentDomain.TECHNICAL], "LONG")

        result = HistoricalAnalogOverrideStage().execute(_ctx(), belief, opinions)

        assert result.strength == 0.3521
    finally:
        _reset_defaults()


def test_enabled_but_regime_does_not_match_leaves_belief_unchanged():
    _reset_defaults()
    _enable_override()
    _save_report([_GATE_ELIGIBLE_ANALOG])  # bullish_normal
    try:
        belief = Belief(direction="LONG", strength=0.3521)
        opinions = _opinions([AgentDomain.SENTIMENT, AgentDomain.TECHNICAL], "LONG")

        result = HistoricalAnalogOverrideStage().execute(
            _ctx(trend="bearish", volatility_regime="high"), belief, opinions
        )

        assert result.strength == 0.3521
    finally:
        _reset_defaults()


def test_enabled_but_domains_dont_match_leaves_belief_unchanged():
    """Bilinen analog (sentiment+technical) bu kararda HİÇ anlaşmamış —
    sadece macro anlaşmış — override edilmemeli."""
    _reset_defaults()
    _enable_override()
    _save_report([_GATE_ELIGIBLE_ANALOG])
    try:
        belief = Belief(direction="LONG", strength=0.3521)
        opinions = _opinions([AgentDomain.MACRO], "LONG")

        result = HistoricalAnalogOverrideStage().execute(_ctx(), belief, opinions)

        assert result.strength == 0.3521
    finally:
        _reset_defaults()


def test_enabled_but_direction_is_wait_leaves_belief_unchanged():
    _reset_defaults()
    _enable_override()
    _save_report([_GATE_ELIGIBLE_ANALOG])
    try:
        belief = Belief(direction="WAIT", strength=0.3521)
        opinions = _opinions([AgentDomain.SENTIMENT, AgentDomain.TECHNICAL], "LONG")

        result = HistoricalAnalogOverrideStage().execute(_ctx(), belief, opinions)

        assert result.strength == 0.3521
    finally:
        _reset_defaults()


def test_enabled_with_no_saved_report_leaves_belief_unchanged():
    """Fail-open: rapor hiç oluşmamışsa (yeni kurulum) hiçbir zaman override edilmez."""
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("historical_analog_override_enabled", "true", updated_by="test")
    try:
        belief = Belief(direction="LONG", strength=0.3521)
        opinions = _opinions([AgentDomain.SENTIMENT, AgentDomain.TECHNICAL], "LONG")

        # (Kasıtlı olarak _save_report çağrılmadı — get_latest() None dönebilir
        # ya da paylaşılan test DB'sinde eski bir rapor bulunabilir; her iki
        # durumda da bu SPESİFİK sembol/rejim/domain kombinasyonu gerçek bir
        # kayıtla eşleşmeyeceği için davranış aynı: override edilmez.)
        result = HistoricalAnalogOverrideStage().execute(
            _ctx(trend="testregimeneverused", volatility_regime="x"), belief, opinions
        )

        assert result.strength == 0.3521
    finally:
        _reset_defaults()


def test_multiple_matches_picks_the_highest_win_rate():
    _reset_defaults()
    _enable_override()
    weaker = {**_GATE_ELIGIBLE_ANALOG, "domains": ["sentiment"], "win_rate": 0.80}
    stronger = {**_GATE_ELIGIBLE_ANALOG, "domains": ["technical"], "win_rate": 0.98}
    _save_report([weaker, stronger])
    try:
        belief = Belief(direction="LONG", strength=0.3521)
        opinions = _opinions([AgentDomain.SENTIMENT, AgentDomain.TECHNICAL], "LONG")

        result = HistoricalAnalogOverrideStage().execute(_ctx(), belief, opinions)

        assert result.strength == 0.98
    finally:
        _reset_defaults()
