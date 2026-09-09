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

from analytics.measurement_stability import compute_stability

MIN_SAMPLE_SIZE = 20


def compute_feature_ic(closed_trades: list[dict], min_sample_size: int = MIN_SAMPLE_SIZE) -> dict[str, dict]:
    """closed_trades: DecisionPersistor.list_closed_trades()'in döndürdüğü
    ham satırlar — her birinde agent_contributions (liste; her öge ya bir
    AgentOpinion.model_dump()'u ya da {"type":..., "data":...} zarfı) ve
    direction/entry_price/exit_price sütunları bulunur.

    Her isimli feature için: (o feature'ın ajan skoruna GERÇEK sayısal
    katkısı, ileri fiyat getirisi) çiftleri toplanıp Pearson korelasyonu
    hesaplanıyor.

    FAZ 470 (2026-09-09) — HEDEF DEĞİŞTİ, ÇÜNKÜ ESKİSİ METRİĞİ BOZUYORDU.
    Eskiden hedef `(exit_price - entry_price)/entry_price` idi; bu ileri
    fiyat DEĞİL, işlemin KENDİ bariyer çıkışı (stop/target). Bir dış
    inceleme `autocorrelation_momentum` için IC=0,9924 (n=33) bulup
    "target leakage" şüphesi bildirdi. İzlendi ve sebep bulundu — sızıntı
    feature'da DEĞİL, metrikte:

      katkı = −1,5 olan işlemlerin bariyer getirisi: −4,50 … −4,73%
      katkı = +1,5 olan işlemlerin bariyer getirisi: −0,24 … −0,65%

    İkili bir feature (±1,5) + iki DAR banda kümelenmiş, hiç örtüşmeyen
    bir hedef = Pearson korelasyonu zorunlu olarak ±1'e saturasyona
    gidiyor. Yani raporlanan uç IC'ler (0,9924 / 0,6558 / −0,8566 ...)
    gerçek öngörü gücü değil, bariyer yerleşiminin artefaktıydı.

    Feature'ın KENDİSİ temiz: `_autocorrelation` sadece geçmiş getirilerin
    lag-1 korelasyonu, hiçbir ileri bilgi kullanmıyor. Üstelik DOĞRU
    hedefle ölçüldüğünde gerçekten iyi bir sinyal (+1,5 -> %65,2 yükseliş,
    −1,5 -> %31,6; ayrım +0,336).

    Artık hedef `forward_return` (sabit ufuklu, bariyerden BAĞIMSIZ) —
    `analytics/forward_direction.py`/Faz 466'nın meta-learning
    düzeltmesiyle AYNI ilke. Çıktıdaki `target` alanı hangi hedefin
    kullanıldığını AÇIKÇA söylüyor ki bir daha kimse yanlış okumasın. Bir sinyal SADECE gerçekten
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
    # Faz 470 — hedef takibi ÖZELLİK BAZINDA. İlk sürümde global bir
    # sayaç kullanıldı ve tek bir eski kayıt bile TÜM özellikleri
    # "barrier_exit" diye etiketliyordu; bu, düzeltmenin amacını
    # (hangi sayıya güvenilir olduğunu göstermek) boşa çıkarıyordu.
    forward_counts: dict[str, int] = defaultdict(int)

    for trade in closed_trades:
        entry_price = trade.get("entry_price")
        forward_return = trade.get("forward_return")
        if forward_return is not None:
            raw_return = float(forward_return)
        else:
            # Geriye dönük uyumluluk: forward_return taşımayan çağrılar
            # (eski testler/eski kayıtlar) hâlâ çalışsın, AMA sonuç
            # `target` alanında açıkça "barrier_exit" diye işaretlensin.
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
                if forward_return is not None:
                    forward_counts[feature_name] += 1

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
            # Faz 470: hangi hedefe karşı ölçüldüğü GİZLENMİYOR. Bariyer
            # hedefi ±1'e saturasyona gittiği için uç IC'ler o modda
            # güvenilmezdir; "mixed" ise iki hedef karışmış demektir ve
            # sayı yine ihtiyatla okunmalıdır.
            "target": (
                "forward_return" if forward_counts[feature_name] == len(pairs)
                else "barrier_exit" if forward_counts[feature_name] == 0
                else "mixed"
            ),
            "forward_return_fraction": round(forward_counts[feature_name] / len(pairs), 4),
        }
    return results


def attach_ic_stability(features: dict[str, dict], past_snapshots: list[dict]) -> None:
    """Faz 407 — kullanıcı isteği: "ölçtüğümüz her veri için zaman
    içindeki stabilitesini de ölçelim." historical_analog_gatherer.py/
    agent_combination_reliability_gatherer.py'deki AYNI desen: SADECE
    gözlem, hiçbir feature filtrelenmiyor/pasifleştirilmiyor — bir
    feature'ın IC'si haftadan haftaya istikrarlı mı yoksa gürültülü mü
    (ör. korelasyondaki BTC-ETH/NVDA-AMD ayrımıyla AYNI mantık) ekliyor.
    past_snapshots: FeatureICReportRepository.get_recent()'ın döndürdüğü
    ham liste (her biri {'features': {feature_name: {'ic': ...}}})."""
    past_by_feature: dict[str, list[float]] = {}
    for snap in past_snapshots:
        for name, stat in (snap.get("features") or {}).items():
            past_by_feature.setdefault(name, []).append(stat.get("ic"))

    for name, stat in features.items():
        series = [*past_by_feature.get(name, []), stat.get("ic")]
        stat["ic_stability"] = compute_stability(series)
