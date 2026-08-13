"""Epistemology Agent — "ne kadar gerçekten biliyoruz" meta-uzmanı.

Yön tahmini yapmaz. Mevcut verinin tamlığını/tazeliğini ölçüp, veri
zayıfsa yüksek-güvenli bir WAIT görüşü üreterek council'in genel
konviksiyonunu gerçekçi şekilde dengeler (AgentDebate._synthesize()
WAIT'i de oy olarak sayıyor — bu ajan sessiz değil, gerçek bir ağırlığı
var)."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.epistemology import EpistemologyContext


class EpistemologyAgent:
    def __init__(self):
        self.agent_id = "epistemology_agent_v1"

    def analyze(self, context: EpistemologyContext) -> AgentOpinion:
        evidence = []
        caveats = []

        if context.feature_completeness >= 0.8:
            evidence.append(f"Feature completeness {context.feature_completeness:.0%} — strong data foundation")
            wait_confidence = 0.2
        elif context.feature_completeness >= 0.5:
            caveats.append(f"Feature completeness only {context.feature_completeness:.0%}")
            wait_confidence = 0.5
        else:
            caveats.append(f"Feature completeness critically low ({context.feature_completeness:.0%}) — decision should not be trusted")
            wait_confidence = 0.8

        if context.known_unknown_count > 0:
            caveats.append(f"{context.known_unknown_count} expected feature(s) missing or defaulted")

        if context.data_age_seconds > 300:
            caveats.append(f"Data is {context.data_age_seconds:.0f}s old — may be stale")
            wait_confidence = min(wait_confidence + 0.2, 0.9)

        # Faz 268-sonrası: Data Quality Scoring — signal_engine.compute_
        # data_quality_score'un tespit ettiği fiyat spike/wick manipülasyonu
        # (kötü print) şüphesi. data_age_seconds ile AYNI desen: veri
        # şüpheliyken güveni artırıyor, kendi başına bir yön belirlemiyor.
        if context.data_quality_score < 0.9:
            caveats.append(
                f"Data quality score {context.data_quality_score:.0%} — possible price spike/wick "
                "manipulation detected in recent bars"
            )
            wait_confidence = min(wait_confidence + 0.2, 0.9)

        # data_quality alanı iki BAĞIMSIZ sinyalin daha kötümser olanı —
        # biri iyi görünürken diğerinin gerçek bir sorunu maskelemesini
        # önlemek için ortalama değil min.
        data_quality = min(context.feature_completeness, context.data_quality_score)

        return AgentOpinion(
            agent_id=self.agent_id,
            domain=AgentDomain.EPISTEMOLOGY,
            direction="WAIT",
            confidence=round(wait_confidence, 3),
            evidence_strength=0.6,
            data_quality=round(data_quality, 3),
            freshness=max(0.0, 1.0 - context.data_age_seconds / 600),
            source_reliability=0.85,
            evidence=evidence,
            caveats=caveats,
        ).recalculate()
