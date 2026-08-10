"""Macro Agent — ekonomik göstergelerden piyasa yönü çıkarır."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.macro import MacroContext


class MacroAgent:
    def __init__(self):
        self.agent_id = "macro_agent_v1"

    def analyze(self, context: MacroContext) -> AgentOpinion:
        evidence = []
        caveats = []
        score = 0.0

        # Enflasyon
        if context.inflation_trend == "rising":
            score -= 1.0
            evidence.append("Inflation pressure increasing")
        elif context.inflation_trend == "falling":
            score += 1.0
            evidence.append("Inflation cooling")

        # Likidite — Faz 215: gerçek bulgu — sadece "tight" cezalandırılıyordu,
        # "loose" (genişleyen M2 para arzı — tarihsel olarak risk
        # varlıkları için destekleyici) hiç ödüllendirilmiyordu. Asimetrik:
        # ajan likiditenin sadece kötü tarafını görebiliyordu.
        if context.liquidity_condition == "tight":
            score -= 1.0
            evidence.append("Liquidity conditions restrictive")
        elif context.liquidity_condition == "loose":
            score += 1.0
            evidence.append("Liquidity conditions expansionary")

        # Faz 267 — kullanıcı bulgusu: "devletler borçlarını dört yıllık
        # dönemlerle öder, bu döngü tamamlanınca piyasaya likidite girer."
        # liquidity_condition (yukarıda, M2SL) bunu yakalayamıyor — aylık,
        # yavaş. net_liquidity_trend (Fed bilançosu - Hazine nakit hesabı
        # - ters repo) haftalık/günlük, çok daha hızlı. Boş string ("veri
        # yok", API/key eksikse) hiçbir puan vermiyor — icat edilmiş bir
        # nötr varsayım değil. DİKKAT: bu yeni bir sinyal, henüz gerçek
        # kapanmış işlemlerle doğrulanmadı (bkz. Faz 258'in volume_
        # confirmation'da yaptığı gibi bir feature-importance ölçümü
        # bekliyor) — ağırlığı kasıtlı olarak diğer köklü sinyallerle aynı
        # (±1.0), ne fazla ne az güveniliyor.
        if context.net_liquidity_trend == "expanding":
            score += 1.0
            evidence.append("Net liquidity (Fed balance sheet - TGA - reverse repo) expanding")
        elif context.net_liquidity_trend == "contracting":
            score -= 1.0
            evidence.append("Net liquidity (Fed balance sheet - TGA - reverse repo) contracting")

        # Merkez bankası
        if context.central_bank_bias == "hawkish":
            score -= 1.0
            evidence.append("Central bank stance hawkish")
        elif context.central_bank_bias == "dovish":
            score += 1.0
            evidence.append("Central bank stance supportive")

        # İstihdam — Faz 268h kritik bulgu: Faz 215'in liquidity_condition
        # için düzelttiği AYNI asimetri burada da vardı — sadece
        # "weakening" cezalandırılıyordu, fetch_employment_trend()'in
        # döndürebildiği "improving" hiçbir zaman ödüllendirilmiyordu.
        # Ajan istihdamın sadece kötü tarafını görebiliyordu.
        if context.employment_trend == "weakening":
            score -= 0.5
            evidence.append("Employment trend weakening")
        elif context.employment_trend == "improving":
            score += 0.5
            evidence.append("Employment trend improving")

        if score > 0:
            direction = "LONG"
        elif score < 0:
            direction = "SHORT"
        else:
            direction = "WAIT"

        confidence = min(abs(score) / 3.0, 1.0)

        return AgentOpinion(
            agent_id=self.agent_id,
            domain=AgentDomain.MACRO,
            direction=direction,
            confidence=round(confidence, 3),
            evidence_strength=0.7,
            data_quality=0.8,
            freshness=0.9,
            source_reliability=0.9,
            evidence=evidence,
            caveats=caveats,
        ).recalculate()
