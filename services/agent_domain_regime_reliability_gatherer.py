"""Agent Domain × Regime Reliability'nin girdisini GERÇEK kapanmış
kararlardan toplayan tek kaynak — Faz 364-devam, kullanıcı sorusu: "hangi
ajan hangi rejimde isabetli, ölçmezsek bilemeyiz."

analytics/agent_combination_reliability.py agreeing_domains_for_decision
ile bir kararda final_direction ile AYNI yönde oy veren domain'leri zaten
çıkarıyor. analytics/strategy_regime_compatibility.py ise {'strategy',
'market_regime', 'win'} kayıtlarını strateji × rejim'e göre gruplayıp
win_rate + CI + genel-ortalamaya-göre-delta hesaplıyor — "strategy"
alanı sadece bir etiket, bir domain adı da olabilir. Bu yüzden yeni bir
saf fonksiyon YAZILMADI: her kapanmış kararı, o kararda anlaşan HER
domain için ayrı bir {'strategy': domain, ...} kaydına açıp AYNI saf
fonksiyona besliyoruz.

pump_fade_v1 hariç (council oylaması yok — agent_combination_reliability
ile AYNI dışlama gerekçesi). Kasıtlı olarak SADECE ölçüm/rapor — hiçbir
ajan ağırlığını burada otomatik değiştirmiyor."""
from analytics.agent_combination_reliability import agreeing_domains_for_decision
from analytics.strategy_regime_compatibility import compute_strategy_regime_compatibility
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_DECISIONS = 2000


def gather_agent_domain_regime_reliability() -> dict:
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=MAX_DECISIONS, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )

    records = []
    for t in closed_trades:
        contributions = t.get("agent_contributions")
        final_direction = t.get("direction")
        market_regime = t.get("market_regime")
        pnl = t.get("pnl")
        if not contributions or not final_direction or market_regime is None or pnl is None:
            continue
        agreeing = agreeing_domains_for_decision(contributions, final_direction)
        if not agreeing:
            continue
        win = pnl > 0
        for domain in agreeing:
            records.append({"strategy": domain, "market_regime": market_regime, "win": win})

    by_domain = compute_strategy_regime_compatibility(records)
    return {"by_domain": by_domain, "n_trades": len(closed_trades)}
