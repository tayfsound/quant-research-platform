"""Credit Agent — tahvil piyasası kredi koşullarından piyasa yönü çıkarır.
Faz 333, kullanıcı isteği (harici bir AI incelemesinin önerdiği ilk yeni
ajan): "credit leads equity" — tahvil piyasası sinyalleri risk
varlıklarından (hisse/kripto) ÖNCE gelir."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.credit import CreditContext


class CreditAgent:
    def __init__(self):
        self.agent_id = "credit_agent_v1"

    def analyze(self, context: CreditContext) -> AgentOpinion:
        evidence = []
        caveats = []
        contributions: dict[str, float] = {}

        # Yield curve — tersine dönmüş eğri (10Y-2Y negatif) tarihsel
        # olarak en güçlü, en köklü resesyon uyarı sinyallerinden biri.
        # Normal (pozitif) eğri nötr sayılıyor — "eğri düz/normal" tek
        # başına bir "her şey yolunda" sinyali değil, sadece "resesyon
        # uyarısı yok" demek — bu yüzden sadece inverted puanlanıyor,
        # normal ödüllendirilmiyor (MacroAgent'ın liquidity/employment
        # simetrisinden BİLEREK farklı: yield curve inversiyonunun
        # tarihsel gücü asimetrik, "normal" durumun kendisi bir alpha
        # kaynağı değil, sadece "yok" durumu).
        if context.yield_curve_signal == "inverted":
            contributions["yield_curve_signal"] = -1.0
            evidence.append("Getiri eğrisi tersine dönmüş (10Y-2Y negatif) — tarihsel resesyon uyarısı")

        # Kredi spread'i — genişliyorsa piyasa kredi riskini daha pahalı
        # fiyatlıyor (risk-off), daralıyorsa risk-on. MacroAgent'ın
        # liquidity_condition'ıyla AYNI simetrik desen (hem iyi hem kötü
        # taraf ödüllendiriliyor/cezalandırılıyor).
        if context.credit_spread_trend == "widening":
            contributions["credit_spread_trend"] = -1.0
            evidence.append("Yüksek getirili tahvil spread'i genişliyor — kredi koşulları sıkılaşıyor")
        elif context.credit_spread_trend == "narrowing":
            contributions["credit_spread_trend"] = 1.0
            evidence.append("Yüksek getirili tahvil spread'i daralıyor — kredi koşulları gevşiyor")

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
            domain=AgentDomain.CREDIT,
            direction=direction,
            confidence=round(confidence, 3),
            evidence_strength=0.7,
            data_quality=0.8,
            freshness=0.9,
            source_reliability=0.9,
            evidence=evidence,
            caveats=caveats,
            feature_contributions={k: round(v, 4) for k, v in contributions.items()},
        ).recalculate()
