"""Historical Analog Engine'in girdisini GERÇEK kapanmış kararlardan
toplayan tek kaynak — FIL Faz D. analytics/historical_analog_engine.py
saf (pure) kalıyor, gerçek veriye dokunan kod burada. services/agent_
combination_reliability_gatherer.py ile AYNI desen (pump_fade_v1 hariç —
council oylaması yok, mekanik strateji, anlaşma/rejim kavramı anlamsız),
sadece market_regime ve direction'ı da kayda ekliyor.

Faz 404 — dördüncü eksen: market_data.features.market_state_engine::
market_state_reversing_for_decision() ile agent_contributions'tan o
kararın anındaki `reversing` bayrağı çıkarılıyor. SADECE 2026-09-01'den
(Faz 401) SONRAKİ kararlarda bu alan var — daha eski kararlar bu yüzden
dışlanıyor (analytics/historical_analog_engine.py'nin kendi fail-closed
filtresi).

Faz 450 (2026-09-08) — kullanıcının 2026-09-06 kararının 7 boyutunun
TAMAMI: `market_snapshot` girdisinin ZATEN kaydettiği `features.
volatility_regime` (signal_engine.py'nin ham çıktısı) ve `raw_snapshot.
structure_phase` (Wyckoff, pattern_signals) + `strategy_regime_
compatibility_gatherer.py::_trade_type()`'ın (Faz 425/426, entry_price/
stop_loss_price'tan scalp/swing) YENİDEN KULLANIMI — hiçbiri yeni bir
veri kaynağı GEREKTİRMİYOR, üçü de zaten her kararda kaydediliyor."""
from analytics.agent_combination_reliability import agreeing_domains_for_decision
from analytics.evaluation_cohort import describe_evaluation_window
from analytics.historical_analog_engine import compute_historical_analogs
from analytics.measurement_stability import compute_stability
from market_data.features.market_state_engine import market_state_reversing_for_decision
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET
from services.strategy_regime_compatibility_gatherer import _trade_type

MAX_DECISIONS = 2000
STABILITY_LOOKBACK_SNAPSHOTS = 12


def _analog_key(analog: dict) -> str:
    # Faz 450 (2026-09-08) — .get() İLE OKUNUYOR (doğrudan [...] DEĞİL):
    # geçmiş raporlar (historical_analog_snapshots) bu 3 yeni eksenden
    # ÖNCEKİ (Faz 450 öncesi) şekilde kaydedilmiş olabilir — win_rate_
    # stability karşılaştırması eski/yeni format arasında KeyError ile
    # çökmemeli, sadece eski satırlar "unknown" bucket'ına düşüp yeni
    # formatla ASLA çakışmayan (kasıtlı olarak ayrı) bir anahtar üretmeli.
    return (
        "|".join(sorted(analog["domains"]))
        + f"::{analog.get('market_regime')}::{analog.get('direction')}::{analog.get('reversing')}"
        + f"::{analog.get('volatility_regime')}::{analog.get('structure_phase')}::{analog.get('trade_type')}"
    )


def _market_snapshot_data(agent_contributions: list[dict]) -> dict:
    """`services/decision_recorder.py`'nin `{'type': 'market_snapshot',
    'data': {'features': ctx.market.features, 'raw_snapshot': ctx.market.
    raw_snapshot}}` girdisi — volatility_regime `features` içinde
    (signal_engine.py'nin ham çıktısı), structure_phase `raw_snapshot`
    içinde (pattern_signals, ctx.market.features'a HİÇ karışmıyor)."""
    for item in agent_contributions or []:
        if isinstance(item, dict) and item.get("type") == "market_snapshot":
            return item.get("data") or {}
    return {}


def _attach_win_rate_stability(analogs: list[dict], past_snapshots: list[dict]) -> None:
    """Faz 407 — kullanıcı isteği: "ölçtüğümüz her veri için zaman
    içindeki stabilitesini de ölçelim." SADECE gözlem — hiçbir kovayı
    filtrelemiyor/reddetmiyor, sadece AYNI kovanın win_rate'inin geçmiş
    snapshot'lar arasında ne kadar tutarlı olduğunu ekliyor. Yeterli
    geçmiş (>=2 GERÇEK ölçüm) birikene kadar fail-closed None (in-place
    mutasyon, çağıranın zaten elindeki `analogs` listesini değiştirir)."""
    past_by_key: dict[str, list[float]] = {}
    for snap in past_snapshots:
        for a in (snap.get("result") or {}).get("analogs") or []:
            past_by_key.setdefault(_analog_key(a), []).append(a.get("win_rate"))

    for a in analogs:
        key = _analog_key(a)
        series = [*past_by_key.get(key, []), a.get("win_rate")]
        a["win_rate_stability"] = compute_stability(series)


def gather_historical_analogs() -> dict:
    from database.repositories.decision_persistor import DecisionPersistor
    from database.repositories.historical_analog_report_repository import (
        HistoricalAnalogReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=MAX_DECISIONS, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )
        past_snapshots = HistoricalAnalogReportRepository(session).get_recent(STABILITY_LOOKBACK_SNAPSHOTS)

    records = []
    for t in closed_trades:
        contributions = t.get("agent_contributions")
        final_direction = t.get("direction")
        market_regime = t.get("market_regime")
        pnl = t.get("pnl")
        if not contributions or not final_direction or not market_regime or pnl is None:
            continue
        agreeing = agreeing_domains_for_decision(contributions, final_direction)
        if agreeing is None:
            continue
        snapshot = _market_snapshot_data(contributions)
        volatility_regime = (snapshot.get("features") or {}).get("volatility_regime")
        structure_phase = (snapshot.get("raw_snapshot") or {}).get("structure_phase")
        trade_type = _trade_type(t.get("entry_price"), t.get("stop_loss_price"))
        records.append({
            "agreeing_domains": agreeing,
            "market_regime": market_regime,
            "direction": final_direction,
            "reversing": market_state_reversing_for_decision(contributions),
            "volatility_regime": volatility_regime,
            "structure_phase": structure_phase,
            "trade_type": trade_type,
            "win": pnl > 0,
            "closed_at": t.get("closed_at"),
        })

    result = compute_historical_analogs(records)
    _attach_win_rate_stability(result["analogs"], past_snapshots)
    result["n_trades"] = len(records)
    result["evaluation_window"] = describe_evaluation_window(
        closed_trades, limit=MAX_DECISIONS, exclude_experiment_buckets=[PUMP_FADE_EXPERIMENT_BUCKET],
    )
    return result
