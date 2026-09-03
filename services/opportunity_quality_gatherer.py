"""Opportunity Quality / Meta-Labeling'in girdisini GERÇEK kapanmış
işlemlerden toplayan tek kaynak — Cognitive Core 2.0 (Faz 569-593).
analytics/opportunity_quality.py::compute_agent_agreement()/
compute_opportunity_quality_by_agreement() saf (pure) kalıyor — gerçek
veriye dokunan kod burada.

Her kapanmış işlemin decisions.agent_contributions'ındaki GERÇEK ajan
oylarından (api/rest/positions.py::explain_position ile AYNI çıkarım
deseni) LONG/SHORT/WAIT sayımı yapılır, compute_agent_agreement ile
0-1 arası bir anlaşma skoruna çevrilir — pump_fade_v1 hariç (mekanik
strateji, council oylaması hiç yok)."""
from analytics.evaluation_cohort import describe_evaluation_window
from analytics.feature_relationship import compute_feature_redundancy, compute_redundancy_clusters
from analytics.measurement_stability import compute_stability
from analytics.opportunity_quality import (
    _feature_independence_from_contributions,
    _reliability_from_contributions,
    agreement_from_contributions,
    compute_opportunity_quality_by_agreement,
    compute_opportunity_quality_by_score,
    compute_quality_score,
)
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

STABILITY_LOOKBACK_SNAPSHOTS = 12


def _agreement_for_decision(row: dict) -> float | None:
    return agreement_from_contributions(row.get("agent_contributions"))


def _attach_stability(by_agreement: dict[str, dict], by_quality_score: dict[str, dict], past_snapshots: list[dict]) -> None:
    """Faz 407 — kullanıcı isteği: "ölçtüğümüz her veri için zaman
    içindeki stabilitesini de ölçelim." SADECE gözlem — by_regime alt-
    kırılımına dokunmuyor (örneklem zaten oraya kadar seyrek)."""
    past_agreement: dict[str, list[float]] = {}
    past_score: dict[str, list[float]] = {}
    for snap in past_snapshots:
        result = snap.get("result") or {}
        for bucket, stat in (result.get("by_agreement_bucket") or {}).items():
            past_agreement.setdefault(bucket, []).append(stat.get("win_rate"))
        for bucket, stat in (result.get("by_quality_score_bucket") or {}).items():
            past_score.setdefault(bucket, []).append((stat.get("overall") or {}).get("win_rate"))

    for bucket, stat in by_agreement.items():
        stat["win_rate_stability"] = compute_stability([*past_agreement.get(bucket, []), stat.get("win_rate")])
    for bucket, stat in by_quality_score.items():
        overall = stat.get("overall") or {}
        overall["win_rate_stability"] = compute_stability([*past_score.get(bucket, []), overall.get("win_rate")])


def gather_opportunity_quality() -> dict:
    from database.repositories.decision_persistor import DecisionPersistor
    from database.repositories.opportunity_quality_report_repository import (
        OpportunityQualityReportRepository,
    )
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        past_snapshots = OpportunityQualityReportRepository(session).get_recent(STABILITY_LOOKBACK_SNAPSHOTS)
        # Faz 363 — kullanıcı bulgusu: "high" (yüksek anlaşma) kovası
        # sürekli boş görünüyordu. Kök neden: limit=2000, en yeni 2000
        # kapanmış işlemle sınırlıyordu — gerçek toplam 3264 (excluded_
        # from_stats=false, temiz veri), en eski 1264 işlem hiç
        # görülmüyordu. Diğer gatherer'ların aksine (agent_ablation/
        # agent_combination_reliability KASITLI son N pencereyle
        # çalışıyor) burası nadir-olay (near-unanimous konsensüs)
        # tespiti yapıyor — küçük bir kovanın örneklem büyüklüğü tam
        # olarak toplam popülasyona duyarlı, recency-window burada
        # yanlış araç. Kullanıcı isteği: "yapabildiğin kadar geniş yap" —
        # limit=None (list_open_positions'ın Faz 269-sonrası desenindeki
        # AYNI mekanizma) gerçekten sınırsız, tüm zamanların toplamı.
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=None, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )

    # Faz 375-devam (2026-08-29) — kullanıcı isteği: "feature_independence"
    # çarpanı. analytics/feature_relationship.py::compute_redundancy_
    # clusters (Faz B, TEK KAYNAK) AYNI closed_trades'ten GLOBAL redundancy
    # kümelerini bir KEZ hesaplıyor — her karar için yeniden hesaplanmıyor
    # (pahalı olurdu), aynı klikler tüm kararlara uygulanıyor.
    redundancy = compute_feature_redundancy(closed_trades)
    clusters = compute_redundancy_clusters(redundancy)

    trades = []
    score_trades = []
    for t in closed_trades:
        agreement = _agreement_for_decision(t)
        pnl = t.get("pnl")
        if agreement is None or pnl is None:
            continue
        trades.append({"agent_agreement": agreement, "win": pnl > 0})

        # Faz B (2026-08-29) — kullanıcı isteği: ham agreement yerine
        # anlaşma×güvenilirlik×bağımsızlık bileşik skoru. Güvenilirlik
        # hesaplanamıyorsa (ör. eski kayıtlarda source_reliability hiç
        # yoktu) bu karar sürekli-skor tablosundan fail-closed dışlanır —
        # icat edilmiş bir "nötr" güvenilirlik asla varsayılmaz (ama eski
        # agreement-only tabloyu etkilemez, o hâlâ tüm kayıtları kapsıyor).
        # feature_independence ise hesaplanamazsa (feature verisi yoksa)
        # nötr 1.0'a düşer — ham feature verisi olmayan eski kayıtları
        # dışlamak yerine, sadece o boyutta ceza/ödül uygulamaz.
        mean_reliability = _reliability_from_contributions(t.get("agent_contributions"), t.get("direction"))
        if mean_reliability is not None:
            feature_independence = _feature_independence_from_contributions(
                t.get("agent_contributions"), t.get("direction"), clusters,
            )
            score_trades.append({
                "quality_score": compute_quality_score(
                    agreement, mean_reliability,
                    feature_independence if feature_independence is not None else 1.0,
                ),
                "win": pnl > 0,
                "pnl": pnl,
                "market_regime": t.get("market_regime"),
            })

    by_agreement = compute_opportunity_quality_by_agreement(trades)
    by_quality_score = compute_opportunity_quality_by_score(score_trades)
    _attach_stability(by_agreement, by_quality_score, past_snapshots)
    return {
        "by_agreement_bucket": by_agreement,
        "by_quality_score_bucket": by_quality_score,
        "n_trades": len(trades),
        "n_trades_with_reliability": len(score_trades),
        "evaluation_window": describe_evaluation_window(
            closed_trades, limit=None, exclude_experiment_buckets=[PUMP_FADE_EXPERIMENT_BUCKET],
        ),
    }
