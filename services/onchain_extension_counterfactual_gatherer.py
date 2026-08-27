"""OnChain BTC-Kısıtı Uzatma Karşı-Olgusalı'nın girdisini GERÇEK
kapanmış kararlardan toplayan tek kaynak — backlog #51.
analytics/onchain_extension_counterfactual.py saf kalıyor.

services/counterfactual_agent_impact_gatherer.py'nin replay_flipped_
decision'ını (bar-bar risk/execution replay, ~150 satır, TEK kaynak)
resynth parametresiyle doğrudan çağırıyor — kopyalanmıyor.

Talep üzerine çağrılır (Faz 363'teki AYNI ilke) — hiçbir celery
task'ına bağlanmıyor, Binance hız sınırlayıcısı yüzünden her replay'den
sonra kibarlık gecikmesi var."""
import time
from datetime import datetime

from analytics.onchain_extension_counterfactual import resynthesize_with_onchain_btc_extension
from services.counterfactual_agent_impact_gatherer import _load_breakeven_settings, replay_flipped_decision
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

REPLAY_POLITENESS_DELAY_SECONDS = 0.3


def _btc_onchain_timeline() -> list[tuple[datetime, float, float]]:
    """Gerçek BTCUSDT kararlarının onchain oylarından, zaman sıralı
    (network_activity_trend_contribution, hash_rate_trend_contribution)
    dizisi — BTC-DIŞI kararlara "o an BTC ağı nasıldı" sorusunu cevaplamak
    için. is_btc=True olduğu her karar için ikisi de (varsayılan 0.0,
    eşik aşılmadıysa gerçekten sıfır) mevcut."""
    from database.session_factory import SessionFactory
    from sqlalchemy import text

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                """
                SELECT timestamp, agent_contributions FROM decisions
                WHERE symbol = 'BTCUSDT' AND agent_contributions IS NOT NULL
                ORDER BY timestamp ASC
                """
            )
        ).fetchall()

    timeline = []
    for ts, contributions in rows:
        onchain = next(
            (c for c in contributions if isinstance(c, dict) and c.get("domain") == "onchain"), None
        )
        if onchain is None:
            continue
        fc = onchain.get("feature_contributions") or {}
        timeline.append((ts, fc.get("network_activity_trend", 0.0), fc.get("hash_rate_trend", 0.0)))
    return timeline


def _nearest_btc_state(timeline: list[tuple[datetime, float, float]], target: datetime) -> tuple[float, float] | None:
    """Basit doğrusal en-yakın arama — timeline tipik olarak birkaç bin
    satır, ikili arama icat etmeye değecek ölçekte değil (bkz. gerçek
    kullanım: talep üzerine, tek seferlik bir analiz çağrısı)."""
    if not timeline:
        return None
    best = min(timeline, key=lambda row: abs((row[0] - target).total_seconds()))
    return best[1], best[2]


def gather_onchain_btc_extension_counterfactual(max_decisions: int = 500) -> dict:
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=max_decisions, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )
    non_btc_trades = [t for t in closed_trades if t.get("symbol") != "BTCUSDT"]

    timeline = _btc_onchain_timeline()
    breakeven_settings = _load_breakeven_settings()

    results = []
    actual_pnls = []
    n_flipped = 0
    for t in non_btc_trades:
        contributions = t.get("agent_contributions")
        actual_direction = t.get("direction")
        pnl = t.get("pnl")
        opened_at = t.get("opened_at")
        if not contributions or not actual_direction or pnl is None or not opened_at:
            continue

        btc_state = _nearest_btc_state(timeline, opened_at)
        if btc_state is None:
            continue

        resynth = resynthesize_with_onchain_btc_extension(contributions, btc_state[0], btc_state[1])
        if resynth is None:
            continue
        belief, _ = resynth
        if belief.direction in ("WAIT", actual_direction.upper()):
            continue  # flip yok -- bu ölçümün kapsamı dışında
        n_flipped += 1

        replay = replay_flipped_decision(t, "onchain_btc_extension", breakeven_settings, resynth=resynth)
        if replay is None:
            continue
        results.append(replay)
        time.sleep(REPLAY_POLITENESS_DELAY_SECONDS)
        actual_pnls.append(float(pnl))

    traded = [r for r in results if r["would_have_traded"] and r["pnl"] is not None]
    n_wins = sum(1 for r in traded if r["win"])
    counterfactual_total_pnl = sum(r["pnl"] for r in traded)
    actual_total_pnl_same_decisions = sum(actual_pnls)

    verdict = "inconclusive"
    if len(traded) >= 10:
        if counterfactual_total_pnl > actual_total_pnl_same_decisions:
            verdict = "extension_would_have_helped"
        elif counterfactual_total_pnl < actual_total_pnl_same_decisions:
            verdict = "extension_would_have_hurt"
        else:
            verdict = "no_difference"

    return {
        "n_non_btc_decisions_analyzed": len(non_btc_trades),
        "n_flipped_decisions": n_flipped,
        "n_would_have_traded": len(traded),
        "n_rejected_or_no_data": len(results) - len(traded),
        "counterfactual_win_rate": round(n_wins / len(traded), 4) if traded else None,
        "counterfactual_total_pnl": round(counterfactual_total_pnl, 4) if traded else None,
        "actual_total_pnl_same_decisions": round(actual_total_pnl_same_decisions, 4),
        "verdict": verdict,
        "data_leakage_caveat": (
            "Risk-kapısı girdileri ve RiskTargetStage'in kalibrasyon/çarpan okumaları bu replay'in "
            "ÇALIŞTIRILDIĞI ANDAKİ canlı duruma göre, pozisyon büyüklüğü gerçekleşen işlemin GERÇEK "
            "boyutuna göre yaklaşık -- tam tarihsel point-in-time doğruluk değil. Ayrıca 'en yakın "
            "zamanlı BTC durumu' bir yaklaşıklık, o TAM anın BTC ağ durumu değil."
        ),
    }
