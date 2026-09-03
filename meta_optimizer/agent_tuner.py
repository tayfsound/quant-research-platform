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

# Faz 239: raporun önerdiği "[-2.0,+2.0] tüm katsayılar için" sınırı
# gerçek kodun semantiğiyle uyuşmuyor — technical_agent.py'de her katsayı
# zaten bir if/elif dalında +=/-= olarak kullanılıyor (yön dalın kendisinde
# kodlu), yani katsayının kendisi negatif olursa YÖN TERSİNE döner (ör.
# "bullish trend" bulgusu negatif bir trend_weight ile skoru AŞAĞI çeker)
# — bu icat edilmiş bir davranış olur, gerçek TA mantığıyla çelişir. Bu
# yüzden büyüklük (magnitude) katsayıları [0, 2.0]'a, çarpımsal indirim
# (adx_weak_discount) [0, 1.0]'a, ve confidence_divisor (pozitif olmak
# ZORUNDA, 0'a yakınsa confidence patlar) [2.0, 10.0]'a sınırlandı —
# raporun ruhuna (küçük, sınırlı bir arama uzayı) sadık ama koda uyumlu.
FIELD_BOUNDS: dict[str, tuple[float, float]] = {
    "trend_weight": (0.0, 2.0),
    "momentum_weight": (0.0, 2.0),
    "market_structure_weight": (0.0, 2.0),
    "ema_alignment_weight": (0.0, 2.0),
    "rsi_extreme_weight": (0.0, 2.0),
    "volume_confirmation_penalty": (0.0, 2.0),
    "bollinger_confirm_weight": (0.0, 2.0),
    "adx_weak_discount": (0.0, 1.0),
    "adx_strong_confirm_weight": (0.0, 2.0),
    "obv_divergence_weight": (0.0, 2.0),
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
            SELECT direction, pnl, agent_contributions, closed_at
            FROM decisions
            WHERE status='closed' AND excluded_from_stats=false AND closed_at IS NOT NULL
                AND agent_contributions IS NOT NULL
            ORDER BY closed_at DESC
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

        records.append(HistoricalTechnicalRecord(ctx, executed_direction, float(pnl)))

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
    """Her gerçek kayıt için: bu θ ile ajan HANGİ yöne oy verirdi, ve o
    oy gerçek yürütülen yönle aynıysa gerçek pnl, tersse -pnl, WAIT ise 0.
    (position_closer.py::_record_agent_learning'deki was_correct mantığının
    aynısı — burada pnl'e uygulanmış hali.)"""
    agent = TechnicalAgent(coefficients=coefficients)
    pnls = []
    for record in records:
        opinion = agent.analyze(record.context)
        if opinion.direction == record.executed_direction:
            pnls.append(record.pnl)
        elif opinion.direction in ("LONG", "SHORT"):
            pnls.append(-record.pnl)
        else:
            pnls.append(0.0)
    return np.array(pnls)


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

    es = cma.CMAEvolutionStrategy(x0, 0.3, {
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
