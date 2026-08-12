"""Online Feature Selection — Information Coefficient (IC).

Faz 258'in volume_confirmation için MANUEL yaptığı ölçümün ("561 gerçek
kapanmış işlem üzerinden, bu sinyal aslında ne kadar öngörücü?")
genelleştirilmiş, sürekli hali. Feature Importance işi (contracts/
agent.py::AgentOpinion.feature_contributions) sayesinde artık her ajanın
her isimli sinyalinin skora GERÇEK sayısal katkısı decisions.
agent_contributions'a düşüyor — bu modül o katkıyı GERÇEK gerçekleşen
fiyat hareketiyle (IC'nin klasik tanımı: sinyal ile ileri getiri
arasındaki korelasyon) karşılaştırıp hangi sinyallerin şu an gerçekten
öngörücü, hangilerinin gürültü ya da TERS yönde olduğunu ölçüyor.

Kasıtlı olarak SADECE ölçüm/raporlama katmanı — otomatik olarak hiçbir
ajanın skorlamasını DEĞİŞTİRMİYOR. Bu oturumun tekrarlanan ilkesi: AI
kendi skorlama mantığını otomatik gevşetemez/değiştiremez; bir insan
gerçek IC sayılarını görüp KASITLI bir kalibrasyon kararı vermeli —
tıpkı Faz 258'in volume_confirmation'da elle yaptığı gibi, ama artık tek
tek elle ölçmek yerine tüm enstrümante edilmiş sinyaller için otomatik/
sürekli."""
from collections import defaultdict

from scipy import stats

MIN_SAMPLE_SIZE = 20


def compute_feature_ic(closed_trades: list[dict], min_sample_size: int = MIN_SAMPLE_SIZE) -> dict[str, dict]:
    """closed_trades: DecisionPersistor.list_closed_trades()'in döndürdüğü
    ham satırlar — her birinde agent_contributions (liste; her öge ya bir
    AgentOpinion.model_dump()'u ya da {"type":..., "data":...} zarfı) ve
    direction/entry_price/exit_price sütunları bulunur.

    Her isimli feature için: (o feature'ın ajan skoruna GERÇEK sayısal
    katkısı, o işlemdeki GERÇEK ham fiyat getirisi — trade yönünden
    bağımsız, sadece fiyatın gerçekte nereye gittiği) çiftleri toplanıp
    Pearson korelasyonu hesaplanıyor. Bir sinyal SADECE gerçekten
    ateşlendiği (feature_contributions'ta göründüğü) işlemlerde
    örneklemeye giriyor — "bu sinyal bir şey söylediğinde, işaret ettiği
    yön gerçekten tutuyor mu?" sorusunu ölçmek bu.

    Dönen dict: {feature_name: {"ic", "p_value", "sample_size",
    "agent_domain"}}. min_sample_size altında kalan feature'lar hiç
    dönmüyor — fail-closed, istatistiksel olarak anlamsız bir sayı asla
    raporlanmaz (long_term_trend_regime'in "insufficient_data" deseniyle
    aynı disiplin)."""
    samples: dict[str, list[tuple[float, float]]] = defaultdict(list)
    domains: dict[str, str] = {}

    for trade in closed_trades:
        entry_price = trade.get("entry_price")
        exit_price = trade.get("exit_price")
        if not entry_price or exit_price is None:
            continue
        raw_return = (exit_price - entry_price) / entry_price

        opinions = trade.get("agent_contributions") or []
        for item in opinions:
            if not isinstance(item, dict) or "feature_contributions" not in item:
                continue  # risk_evaluation/market_snapshot zarfları ya da eski (henüz enstrümante edilmemiş) kayıtlar
            domain = item.get("domain", "unknown")
            for feature_name, value in (item.get("feature_contributions") or {}).items():
                samples[feature_name].append((value, raw_return))
                domains[feature_name] = domain

    results: dict[str, dict] = {}
    for feature_name, pairs in samples.items():
        if len(pairs) < min_sample_size:
            continue
        contributions = [p[0] for p in pairs]
        returns = [p[1] for p in pairs]
        # Sabit (varyans=0) bir dizi Pearson'ı tanımsız kılar (0/0) — bu
        # SADECE bir feature her zaman AYNI katkıyı üretmişse olur, gerçek
        # bir korelasyon ölçülemez (fail-closed).
        if len(set(contributions)) < 2 or len(set(returns)) < 2:
            continue
        ic, p_value = stats.pearsonr(contributions, returns)
        results[feature_name] = {
            "ic": round(float(ic), 4),
            "p_value": round(float(p_value), 4),
            "sample_size": len(pairs),
            "agent_domain": domains[feature_name],
        }
    return results
