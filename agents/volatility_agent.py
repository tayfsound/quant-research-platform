"""Volatility Agent — Deribit DVOL'dan (kriptonun VIX'i) piyasa stresi
sinyali çıkarır. Faz 336, kullanıcı isteği (harici bir AI incelemesinin
"direction'dan bağımsız, mevcut sistemin eksik bir boyutu" dediği ilk
madde).

Kasıtlı olarak dar kapsamlı: volatilite endekslerinin (VIX dahil) kripto
için net/tutarlı bir "yüksek IV = düşecek" yön ilişkisi literatürde YOK —
CreditAgent'ın yield curve inversion'ıyla AYNI asimetrik disiplin
uygulanıyor, SADECE ani volatilite sıçraması (genel, varlık-sınıfından
bağımsız bir piyasa-stresi göstergesi) puanlanıyor, "sakin" durumun
kendisi bir alpha kaynağı sayılmıyor."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.volatility import VolatilityContext


class VolatilityAgent:
    def __init__(self):
        self.agent_id = "volatility_agent_v1"

    def analyze(self, context: VolatilityContext) -> AgentOpinion:
        evidence = []
        caveats = []
        contributions: dict[str, float] = {}

        if context.dvol_level is not None:
            evidence.append(f"BTC DVOL (implied volatility endeksi): %{context.dvol_level:.1f}")

        # DVOL aniden sıçrıyorsa (>%15/24sa) — genel bir piyasa-stresi
        # göstergesi, risk varlıkları için tarihsel olarak olumsuz.
        # Sakinleşme (falling) DAHA ZAYIF bir sinyal — vol-crush genelde
        # fiyat stabilizasyonuyla birlikte gelir ama net bir yön iddiası
        # değil, o yüzden CreditAgent'ın credit_spread_trend'inden daha
        # düşük ağırlıkta.
        if context.dvol_trend == "spiking":
            contributions["dvol_trend"] = -1.0
            evidence.append("DVOL hızla yükseliyor (>%15/24sa) — piyasa stresi/belirsizlik artıyor")
        elif context.dvol_trend == "falling":
            contributions["dvol_trend"] = 0.5
            evidence.append("DVOL geriliyor (>%15/24sa) — volatilite sakinleşiyor")

        score = sum(contributions.values())

        if score > 0:
            direction = "LONG"
        elif score < 0:
            direction = "SHORT"
        else:
            direction = "WAIT"

        confidence = min(abs(score) / 2.0, 1.0)

        return AgentOpinion(
            agent_id=self.agent_id,
            domain=AgentDomain.VOLATILITY,
            direction=direction,
            confidence=round(confidence, 3),
            evidence_strength=0.6,
            data_quality=0.8,
            freshness=0.85,
            source_reliability=0.8,
            evidence=evidence,
            caveats=caveats,
            feature_contributions={k: round(v, 4) for k, v in contributions.items()},
        ).recalculate()
