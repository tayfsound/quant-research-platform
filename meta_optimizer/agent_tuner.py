"""Faz 239-241 — Online Meta-Learning (CMA-ES ajan katsayı optimizasyonu).

NOT: bu dosya proje kökündeki meta_optimizer/ paketinin İÇİNDE ama onun
mevcut içeriğiyle (ab_runner.py/analyzer.py/orchestrator.py — LLM sistem
prompt'unu A/B testleyen, hiçbir yerden import edilmeyen, ilk commit'ten
kalma başıboş bir taslak) HİÇBİR İLİŞKİSİ YOK. Ayrı bir paket açmak yerine
zaten var olan (ve isim olarak da doğru) meta_optimizer/ dizinine eklendi.

Gerçek bulgu: her ajanın kendi PnL'i tek başına yok — sadece nihai
(fused) kararın PnL'i var. Bu yüzden "θ katsayı vektörü X olsaydı Sharpe
Y olurdu" sorusu, TÜM council'i (8 diğer ajan + fusion + risk) yeniden
çalıştırmadan tam olarak cevaplanamaz — o kadar pahalı/karmaşık bir
motoru bu faz için kurmak yerine, GERÇEK geçmiş kapanmış işlemlerin
GERÇEK feature'larını (decisions.agent_contributions içindeki
market_snapshot) tekrar oynatıp (replay), TechnicalAgent'ın o feature'larla
FARKLI bir θ ile ne yöne oy verirdi'yi hesaplıyoruz; ajanın oyu gerçek
yürütülen yönle aynıysa gerçek pnl'i, ters yönse gerçek pnl'in negatifini
("bu yönde bahis yapılsaydı ne olurdu" tahmini) sentetik bir "bu ajan
tek başına olsaydı" pnl serisi olarak kullanıyoruz. Bu, gerçek veriye
dayanan, ucuz, replay edilebilir ama yaklaşık bir vekil (proxy) —
tam council simülasyonu değil. walk-forward doğrulama (aşağıda) bu
vekilin gerçekten GELECEĞE genelleyip genellemediğini (in-sample ezber
değil) test ediyor."""
from dataclasses import dataclass

import numpy as np
from sqlalchemy import text

from agents.technical_agent import TechnicalAgent, TechnicalAgentCoefficients
from backtest.embargo_walk_forward import EmbargoWalkForwardSplitter
from contracts.technical import TechnicalContext
from services.agent_confidence_model import _normalize_raw_features

# Faz 239 KARARI, Faz 466'DA GERÇEK VERİYLE ÇÜRÜTÜLDÜ.
#
# Faz 239 şöyle demişti: "katsayı negatif olursa YÖN TERSİNE döner (ör.
# 'bullish trend' bulgusu skoru AŞAĞI çeker) — bu İCAT EDİLMİŞ bir
# davranış olur, gerçek TA mantığıyla çelişir." Bu, o günün bilgisiyle
# ilkeli bir karardı; ama dayandığı varsayım ("bullish trend bulgusu
# yükselişe işaret eder") 2026-09-09'da ölçülüp YANLIŞLANDI.
#
# Faz 460/463'ün gerçek ölçümü (n=132.144 sinyal gözlemi, 7 gün, günlük
# tutarlılık + sembol-içi doğrulamayla):
#     trend               separation −0,101  (7/7 gün negatif)
#     momentum            −0,120  (7/7)
#     ema_alignment       −0,105  (7/7)
#     adx_strong_confirm  −0,109  (7/7)
#     bollinger_confirm   −0,209  (5/5)
#     rsi_extreme         +0,172  (7/7 POZİTİF)
#     obv_divergence      +0,107  (6/7 pozitif)
# Yani "bullish trend -> yukarı" varsayımı bu piyasada ve bu ufukta
# GERÇEKTE TERS çalışıyor. Negatif katsayıya izin vermemek, arama
# uzayından DOĞRU ÇÖZÜMÜ dışlıyordu.
#
# SOMUT SONUÇ (kullanıcı bildirimi: "meta learning hâlâ çalışmıyor, hep
# sıfır, kurduğumuzdan beri bir tur bile gerçekleşmedi"): CMA-ES bir
# sinyali sıfıra indirebiliyor ama İŞARETİNİ ÇEVİREMİYORDU, dolayısıyla
# ulaşabildiği en iyi nokta "hepsini sustur" idi ve bu bir iyileşme
# saymıyordu. Son deneme 2026-09-03: n=2998, sharpe_improvement=−0,017,
# gereken +0,4. Bozuk değildi — YANLIŞ UZAYDA arıyordu.
#
# Artık YÖN taşıyan katsayılar [-2.0, +2.0]. Yön taşımayanlar KASITLI
# olarak eski sınırlarında: adx_weak_discount çarpımsal bir indirim
# ([0,1] dışında anlamsız), confidence_divisor pozitif olmak ZORUNDA
# (0'a yakınsa confidence patlar), htf çarpanları ise Faz 316'da
# semantiği korumak için özellikle asimetrik seçilmişti.
_DIRECTIONAL = (-2.0, 2.0)
FIELD_BOUNDS: dict[str, tuple[float, float]] = {
    "trend_weight": _DIRECTIONAL,
    "momentum_weight": _DIRECTIONAL,
    "market_structure_weight": _DIRECTIONAL,
    "ema_alignment_weight": _DIRECTIONAL,
    "rsi_extreme_weight": _DIRECTIONAL,
    "volume_confirmation_penalty": _DIRECTIONAL,
    "bollinger_confirm_weight": _DIRECTIONAL,
    "adx_weak_discount": (0.0, 1.0),
    "adx_strong_confirm_weight": _DIRECTIONAL,
    "obv_divergence_weight": _DIRECTIONAL,
    "confidence_divisor": (2.0, 10.0),
    # Faz 316 — sınırlar semantiği koruyor: agreement çarpanı 1.0'ı asla
    # AŞMAZ (her zaman bir indirim kalır), disagreement çarpanı 1.0'ın
    # ALTINA asla İNMEZ (her zaman bir artış kalır) — CMA-ES ikisinin
    # rolünü birbirine karıştıramaz.
    "htf_agreement_confidence_multiplier": (0.3, 1.0),
    "htf_disagreement_confidence_multiplier": (1.0, 2.0),
}

MIN_RECORDS_TO_OPTIMIZE = 200


@dataclass(frozen=True)
class HistoricalTechnicalRecord:
    context: TechnicalContext
    executed_direction: str  # "LONG" | "SHORT" — gerçekte açılmış işlemin yönü
    pnl: float
    # Faz 466 — SABİT UFUKLU gerçek ileri getiri (varsayılan 1 saat),
    # işlemin kendi stop/target/tutma süresinden TAMAMEN bağımsız.
    # `analytics/forward_direction.py` (Faz 441) ile AYNI hedef tanımı.
    # Veri yoksa None -> o kayıt yön-tabanlı hedeften DÜŞER (fail-closed).
    forward_return: float | None = None


def load_historical_technical_records(window: int = 3000) -> list[HistoricalTechnicalRecord]:
    """Gerçek kapanmış işlemlerden (agent_contributions içindeki gerçek
    market_snapshot feature'ları), technical ajanın gerçekten oy verdiği
    kayıtları, EN SON `window` kayıt, ESKİDEN YENİYE (walk-forward için
    kronolojik) sırayla döner. agent_confidence_model.py::
    _extract_training_rows ile aynı ham veri kaynağı/normalize haritalaması
    — tekerlek yeniden icat edilmedi.

    2026-09-03 — kullanıcı bulgusu: "Meta-Learning Effectiveness haftalardır
    boş, çalışmıyor belli ki." Kök neden: SQL `ORDER BY closed_at ASC LIMIT
    :window` kullanıyordu — kapanmış işlem sayısı `window`'u geçtiği andan
    itibaren bu HER ZAMAN aynı en eski `window` satırı döner, tablo ne kadar
    büyürse büyüsün asla ilerlemez (sibling `_extract_training_rows`'un
    doğru DESC+LIMIT deseninden sapmış). Kanıt: toplam uygun kayıt 6824
    iken pencere hâlâ 2026-08-11 ile 2026-08-24 arasında donmuş kalmıştı —
    en son ~10 günün TÜM verisi walk-forward'a hiç girmiyordu. Düzeltme:
    en son `window` kaydı DESC çekip Python'da kronolojik sıraya çeviriyor
    (sibling fonksiyonla AYNI desen)."""
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        rows = session.execute(text("""
            SELECT d.direction, d.pnl, d.agent_contributions, d.closed_at,
                   COALESCE(d.entry_price, ref.close) AS ref_price,
                   fwd.close AS price_at_horizon
            FROM decisions d
            -- Faz 466: karar anı ve +1 saat fiyatları. Bu oturumdaki tüm
            -- yön ölçümlerinin (Faz 446/458/459/460) kullandığı AYNI
            -- LATERAL desen. LEFT: fiyat bulunamazsa kayıt tamamen
            -- düşmesin, sadece yön-tabanlı hedefe giremesin.
            LEFT JOIN LATERAL (
                SELECT close FROM market_snapshots m
                WHERE m.exchange='binance' AND m.symbol=d.symbol AND m.resolution='1m'
                  AND m.time BETWEEN d.timestamp - interval '3 min' AND d.timestamp + interval '3 min'
                ORDER BY abs(extract(epoch FROM (m.time - d.timestamp))) LIMIT 1
            ) ref ON true
            LEFT JOIN LATERAL (
                SELECT close FROM market_snapshots m
                WHERE m.exchange='binance' AND m.symbol=d.symbol AND m.resolution='1m'
                  AND m.time BETWEEN d.timestamp + interval '55 min' AND d.timestamp + interval '65 min'
                ORDER BY abs(extract(epoch FROM (m.time - (d.timestamp + interval '1 hour')))) LIMIT 1
            ) fwd ON true
            WHERE d.status='closed' AND d.excluded_from_stats=false AND d.closed_at IS NOT NULL
                AND d.agent_contributions IS NOT NULL
            ORDER BY d.closed_at DESC
            LIMIT :limit
        """), {"limit": window}).mappings().all()
    rows = list(reversed(rows))

    records: list[HistoricalTechnicalRecord] = []
    for r in rows:
        executed_direction = (r["direction"] or "").upper()
        pnl = r["pnl"]
        if pnl is None or executed_direction not in ("LONG", "SHORT"):
            continue

        feats = None
        has_technical_opinion = False
        for c in r["agent_contributions"]:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "market_snapshot":
                feats = (c.get("data") or {}).get("features") or {}
            if c.get("domain") == "technical":
                has_technical_opinion = True
        if not feats or not has_technical_opinion:
            continue

        feats = _normalize_raw_features(feats)
        ctx_kwargs = {
            k: v for k, v in feats.items()
            if k in TechnicalContext.model_fields and v is not None
        }
        try:
            ctx = TechnicalContext(**ctx_kwargs)
        except Exception:
            # Bozuk/eksik bir feature dict'i tüm replay'i durdurmasın —
            # o kayıt atlanır (fail-closed: şüpheli veri kullanılmaz).
            continue

        forward_return = None
        ref_price, horizon_price = r["ref_price"], r["price_at_horizon"]
        if ref_price and ref_price > 0 and horizon_price:
            forward_return = (float(horizon_price) - float(ref_price)) / float(ref_price)

        records.append(
            HistoricalTechnicalRecord(ctx, executed_direction, float(pnl), forward_return)
        )

    return records


def clip_vector(vector: list[float]) -> list[float]:
    names = TechnicalAgentCoefficients.field_names()
    return [
        min(max(v, FIELD_BOUNDS[name][0]), FIELD_BOUNDS[name][1])
        for name, v in zip(names, vector, strict=True)
    ]


def synthetic_pnls(
    coefficients: TechnicalAgentCoefficients,
    records: list[HistoricalTechnicalRecord],
) -> np.ndarray:
    """Bu θ ile ajanın oyu, SABİT UFUKLU gerçek ileri getiriye karşı.

    FAZ 466'DA HEDEF DEĞİŞTİ — ikinci yapısal kusurun düzeltmesi.

    ESKİ hedef: ajanın oyu gerçek YÜRÜTÜLEN yönle aynıysa gerçek `pnl`,
    tersse `-pnl`. İki ayrı sorunu vardı:
      (a) `pnl` bir TRADE SONUCU — bariyer yerleşimine, tutma süresine,
          stop'a bağlı. Bu oturumun ana bulgusu tam olarak bu karışıklık:
          "işlem kâr etti mi" ile "fiyat hangi yöne gitti" AYNI hedef
          değil (bkz. analytics/forward_direction.py, Faz 441).
      (b) `-pnl` varsayımı: "ters yönde bahis yapılsaydı sonuç tam
          simetrik olurdu". Bariyerler asimetrik olduğu için (stop
          mesafesi ≠ hedef mesafesi) bu YANLIŞ.

    YENİ hedef: sabit ufuklu (1 saat) gerçek ileri getiri. LONG oyunda
    +getiri, SHORT oyunda −getiri, WAIT'te 0. Bu, "bu yönde bir birim
    bahis yapılsaydı ufuk sonunda ne olurdu"nun GERÇEK cevabı —
    bariyerlerden, tutma süresinden ve icra kapılarından TAMAMEN
    bağımsız. Sharpe ölçeği korunuyor, dolayısıyla scheduler'ın
    MIN_SHARPE_IMPROVEMENT eşiği anlamını koruyor.

    `forward_return`'ü olmayan kayıtlar 0 katkı verir (fail-closed —
    uydurma bir getiri üretilmez); hepsi eksikse çağıran tarafın
    `has_forward_returns()` ile bunu FARK ETMESİ gerekir."""
    agent = TechnicalAgent(coefficients=coefficients)
    returns = []
    for record in records:
        if record.forward_return is None:
            returns.append(0.0)
            continue
        opinion = agent.analyze(record.context)
        if opinion.direction == "LONG":
            returns.append(record.forward_return)
        elif opinion.direction == "SHORT":
            returns.append(-record.forward_return)
        else:
            returns.append(0.0)
    return np.array(returns)


def has_forward_returns(records: list[HistoricalTechnicalRecord]) -> bool:
    """Faz 466 — yön-tabanlı hedef, `forward_return` olmadan SESSİZCE
    her θ için sıfır dizisi üretir ve CMA-ES "hiçbir şey fark etmiyor"
    sonucuna varır. Bu, tam da kullanıcının şikâyet ettiği "hep sıfır"
    durumunun yeni bir kılıkta tekrarı olurdu. Scheduler bu kontrolü
    yapıp sebebi AÇIKÇA raporluyor."""
    return any(r.forward_return is not None for r in records)


def sharpe_like(pnls: np.ndarray) -> float:
    """analytics/metrics/engine.py::sharpe_ratio ile aynı desen — tek
    örneklem ya da sıfır varyansta (std=0) bölme patlamasın diye 0.0'a
    düşülüyor, icat edilmiş bir Sharpe değil."""
    if len(pnls) == 0:
        return 0.0
    std = float(np.std(pnls))
    if std <= 0:
        return 0.0
    return float(np.mean(pnls) / std)


def optimize_technical_agent_coefficients(
    records: list[HistoricalTechnicalRecord],
    max_iterations: int = 100,
    seed: int = 42,
) -> tuple[TechnicalAgentCoefficients, float]:
    """Verilen (train) kayıt kümesinde CMA-ES ile sentetik Sharpe'ı
    maksimize eden θ'yı arar. Başlangıç noktası (x0) MEVCUT sabit
    katsayılar — optimizasyon rastgele bir noktadan değil, bilinen/
    çalışan bir konfigürasyondan başlıyor."""
    import cma

    default = TechnicalAgentCoefficients()
    names = TechnicalAgentCoefficients.field_names()
    x0 = default.as_vector()
    lower = [FIELD_BOUNDS[n][0] for n in names]
    upper = [FIELD_BOUNDS[n][1] for n in names]

    # Faz 466 — BASLANGIC ADIM BOYU (sigma) buyutuldu: 0.3 -> 0.9.
    # Sinirlari negatife acmak TEK BASINA yetmedi; bir testte yakalandi:
    # yon tasiyan katsayilarin arama araligi [0,2]'den [-2,+2]'ye
    # cikinca (genislik 2 -> 4), 0.3'luk adim boyu ISARET SINIRINI
    # asamiyordu. Ajanin yonu bir ESIK fonksiyonu oldugu icin arama
    # yuzeyi basamakli: CMA-ES kucuk adimlarla x0'in (hepsi pozitif
    # varsayilanlar) etrafinda sikisip kaliyor ve dogru cozum (negatif
    # agirliklar) erisilemez kaliyordu. Sentetik ters-piyasa testinde
    # dogrulandi: 0.3 ile hicbir katsayi negatife gecmiyor, 0.9 ile
    # geciyor. CMA-ES icin olagan tavsiye sigma ~ arama araliginin
    # 1/4'u; genislik 4 -> ~1.0, secilen 0.9 bunun hemen altinda.
    es = cma.CMAEvolutionStrategy(x0, 0.9, {
        "bounds": [lower, upper],
        "seed": seed,
        "maxiter": max_iterations,
        "verbose": -9,
    })

    def objective(vector) -> float:
        coeffs = TechnicalAgentCoefficients.from_vector(clip_vector(list(vector)))
        return -sharpe_like(synthetic_pnls(coeffs, records))  # cma minimize eder

    es.optimize(objective)
    best_vector = clip_vector(list(es.result.xbest))
    best_coeffs = TechnicalAgentCoefficients.from_vector(best_vector)
    best_sharpe = -float(es.result.fbest)
    return best_coeffs, best_sharpe


def walk_forward_validate(
    records: list[HistoricalTechnicalRecord],
    train_size: int = 400,
    test_size: int = 100,
    step: int = 100,
    embargo: int = 10,
    max_iterations: int = 80,
) -> dict:
    """Her fold'da TRAIN penceresinde CMA-ES ile θ bulunur, o θ hiç
    görmediği TEST penceresinde (out-of-sample) ölçülür — aynı pencerede
    optimize edip ölçmek (in-sample ezber) YASAK. embargo, backtest/
    embargo_walk_forward.py'deki AYNI desen — train/test sınırında bir
    kayıttaki lookback-feature'ın test tarafına sızmaması için boşluk."""
    splitter = EmbargoWalkForwardSplitter(
        train_size=train_size, test_size=test_size, step=step, embargo=embargo,
    )
    splits = splitter.split(len(records))
    if not splits:
        return {
            "folds": [],
            "mean_oos_sharpe_tuned": None,
            "mean_oos_sharpe_baseline": None,
            "sharpe_improvement": None,
            "sample_count": len(records),
        }

    default = TechnicalAgentCoefficients()
    fold_results = []
    for split in splits:
        train_records = records[split.train_start:split.train_end]
        test_records = records[split.test_start:split.test_end]

        tuned_coeffs, _ = optimize_technical_agent_coefficients(
            train_records, max_iterations=max_iterations,
        )

        oos_tuned = sharpe_like(synthetic_pnls(tuned_coeffs, test_records))
        oos_baseline = sharpe_like(synthetic_pnls(default, test_records))

        fold_results.append({
            "train_range": (split.train_start, split.train_end),
            "test_range": (split.test_start, split.test_end),
            "tuned_coefficients": tuned_coeffs,
            "oos_sharpe_tuned": oos_tuned,
            "oos_sharpe_baseline": oos_baseline,
        })

    mean_tuned = float(np.mean([f["oos_sharpe_tuned"] for f in fold_results]))
    mean_baseline = float(np.mean([f["oos_sharpe_baseline"] for f in fold_results]))

    return {
        "folds": fold_results,
        "mean_oos_sharpe_tuned": mean_tuned,
        "mean_oos_sharpe_baseline": mean_baseline,
        "sharpe_improvement": mean_tuned - mean_baseline,
        "sample_count": len(records),
    }
