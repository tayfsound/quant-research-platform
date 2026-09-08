"""services/council_analog_agreement_gatherer.py — Faz 452 (2026-09-08),
Faz 447'nin kullanıcı onaylı ilk (gözlem-only) adımı. tests/test_
historical_analog_engine.py::test_gate_eligible_requires_fdr_and_oos_
and_effective_sample_size_together İLE AYNI 40+40/40-gün desenle GERÇEK
bir gate_eligible hücre kuruluyor (train, cutoff'tan ÖNCE) — sonra
cutoff'tan SONRAKİ (holdout, GERÇEKTEN tutulmuş) kararlarla bu hücrenin
öngörü değeri test ediliyor."""
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from contracts.agent import AgentDomain, AgentOpinion
from database.session_factory import SessionFactory
from services.council_analog_agreement_gatherer import gather_council_vs_analog_agreement


def _opinion_dict(domain: AgentDomain, direction: str) -> dict:
    o = AgentOpinion(domain=domain, direction=direction, confidence=0.8)
    o.recalculate()
    return o.model_dump(mode="json")


_CONTRIBUTIONS = [
    _opinion_dict(AgentDomain.TECHNICAL, "LONG"),
    _opinion_dict(AgentDomain.MACRO, "LONG"),
    {"type": "market_state", "data": {"reversing": False}},
    {"type": "market_snapshot", "data": {
        "features": {"volatility_regime": "normal"},
        "raw_snapshot": {"structure_phase": "neutral"},
    }},
]
_BASELINE_CONTRIBUTIONS = [
    _opinion_dict(AgentDomain.QUANT, "LONG"),
    {"type": "market_state", "data": {"reversing": False}},
    {"type": "market_snapshot", "data": {
        "features": {"volatility_regime": "normal"},
        "raw_snapshot": {"structure_phase": "neutral"},
    }},
]


def _insert_decision(session, *, symbol: str, timestamp, closed_at, win: bool, contributions: list[dict]) -> None:
    session.execute(
        text("""
            INSERT INTO decisions
                (id, timestamp, symbol, direction, size, confidence, status, entry_price, stop_loss_price,
                 pnl, agent_contributions, market_regime, closed_at, excluded_from_stats)
            VALUES
                (:id, :timestamp, :symbol, 'LONG', 1.0, 0.8, 'closed', 100.0, 99.0,
                 :pnl, CAST(:agent_contributions AS jsonb), 'bullish_low', :closed_at, false)
        """),
        {
            "id": str(uuid.uuid4()), "timestamp": timestamp, "symbol": symbol,
            "pnl": 10.0 if win else -10.0,
            "agent_contributions": json.dumps(contributions, default=str),
            "closed_at": closed_at,
        },
    )


def test_gatherer_finds_a_real_gate_eligible_cell_and_tests_it_on_genuinely_held_out_data():
    symbol = f"CAATEST{uuid.uuid4().hex[:6]}USDT"
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=1)
    train_base = now - timedelta(days=60)  # 40 farkli takvim gunune yayilsin diye cok eski

    with SessionFactory.get_session() as session:
        # train: technical+macro/bullish_low/LONG icin GERCEK bir gate_
        # eligible hucre (test_gate_eligible_requires_fdr_and_oos_and_
        # effective_sample_size_together ILE AYNI 40+40/40-gun deseni).
        for i in range(40):
            ts = train_base + timedelta(days=i)
            _insert_decision(
                session, symbol=symbol, timestamp=ts, closed_at=ts,
                win=(i % 10 != 0), contributions=_CONTRIBUTIONS,
            )
            _insert_decision(
                session, symbol=symbol, timestamp=ts, closed_at=ts,
                win=(i < 10), contributions=_BASELINE_CONTRIBUTIONS,
            )
        # holdout: cutoff'tan SONRA, AYNI baglamda (technical+macro/
        # bullish_low/LONG) 15 karar, hepsi kazanan -- gercekten tutulmus.
        for i in range(15):
            ts = now - timedelta(minutes=i)
            _insert_decision(
                session, symbol=symbol, timestamp=ts, closed_at=ts,
                win=True, contributions=_CONTRIBUTIONS,
            )
        # holdout filler: farkli baglam (quant/bullish_low/LONG), yarisi kazanan.
        for i in range(15, 30):
            ts = now - timedelta(minutes=i)
            _insert_decision(
                session, symbol=symbol, timestamp=ts, closed_at=ts,
                win=(i % 2 == 0), contributions=_BASELINE_CONTRIBUTIONS,
            )
        session.commit()

    result = gather_council_vs_analog_agreement(holdout_hours=1.0)

    assert result["n_gate_eligible_analogs"] >= 1
    agreement = result["agreement"]
    assert agreement is not None
    assert agreement["n_endorsed"] >= 10  # en az test sembolunun 15 holdout karari
    assert agreement["endorsed_win_rate"] == 1.0
    assert agreement["lift"] is not None
