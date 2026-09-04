"""Macro Agent — ekonomik göstergelerden piyasa yönü çıkarır."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.macro import MacroContext


class MacroAgent:
    def __init__(self):
        self.agent_id = "macro_agent_v1"

    def analyze(self, context: MacroContext) -> AgentOpinion:
        evidence = []
        caveats = []
        # Faz 268-sonrası: Feature Importance — bkz. agents/quant_agent.py
        # ve agents/technical_agent.py'deki aynı desen.
        contributions: dict[str, float] = {}

        # Enflasyon
        if context.inflation_trend == "rising":
            contributions["inflation"] = -1.0
            evidence.append("Enflasyon baskısı artıyor")
        elif context.inflation_trend == "falling":
            contributions["inflation"] = 1.0
            evidence.append("Enflasyon yavaşlıyor")

        # Faz 408 (2026-09-03) — kullanıcı bulgusu: macro'nun raw_
        # confidence'ı 1812 gerçek karardan HİÇBİRİNDE farklı çıkmıyordu
        # — hep tam 0.167. Kök neden: liquidity_condition (M2SL, ±1.0) ile
        # net_liquidity_trend (aşağıda) son ~1 aydır sürekli TERS yönde
        # çıkıp toplamda birbirini TAM götürüyordu. İlk düzeltme (aynı gün)
        # liquidity_condition'ı ikincil (±0.5) yaptı.
        #
        # Faz 411 (2026-09-04) — kullanıcı isteği: "gerçekten gürültü
        # olduğunu tespit ettiğimiz bütün sinyalleri mimariden temizleyelim."
        # Rejime göre ayrıştırılmış Feature IC denetiminde liquidity_
        # condition HİÇBİR rejim segmentinde anlamlı çıkmadı (bullish_normal
        # p=0.48, bullish_low p=0.34, bearish_low p=0.09, bearish_high
        # p=0.99, n=6910) — Faz 408'in "ikincil sinyal" uzlaşması yerine
        # artık TAMAMEN kaldırıldı, gerçekten gürültüymüş. net_liquidity_
        # trend (Fed bilançosu - Hazine nakit hesabı - ters repo, aşağıda)
        # zaten daha güncel/ilgili sinyaldi (Faz 267), tek başına kalıyor.
        #
        # Faz 267 — kullanıcı bulgusu: "devletler borçlarını dört yıllık
        # dönemlerle öder, bu döngü tamamlanınca piyasaya likidite girer."
        # Boş string ("veri yok", API/key eksikse) hiçbir puan vermiyor —
        # icat edilmiş bir nötr varsayım değil.
        if context.net_liquidity_trend == "expanding":
            contributions["net_liquidity_trend"] = 1.0
            evidence.append("Net likidite (Fed bilançosu - Hazine nakit hesabı - ters repo) genişliyor")
        elif context.net_liquidity_trend == "contracting":
            contributions["net_liquidity_trend"] = -1.0
            evidence.append("Net likidite (Fed bilançosu - Hazine nakit hesabı - ters repo) daralıyor")

        # Merkez bankası
        if context.central_bank_bias == "hawkish":
            contributions["central_bank_bias"] = -1.0
            evidence.append("Merkez bankası duruşu şahin (hawkish)")
        elif context.central_bank_bias == "dovish":
            contributions["central_bank_bias"] = 1.0
            evidence.append("Merkez bankası duruşu destekleyici (dovish)")

        # İstihdam — Faz 268h kritik bulgu: Faz 215'in liquidity_condition
        # için düzelttiği AYNI asimetri burada da vardı — sadece
        # "weakening" cezalandırılıyordu, fetch_employment_trend()'in
        # döndürebildiği "improving" hiçbir zaman ödüllendirilmiyordu.
        # Ajan istihdamın sadece kötü tarafını görebiliyordu.
        if context.employment_trend == "weakening":
            contributions["employment_trend"] = -0.5
            evidence.append("İstihdam eğilimi zayıflıyor")
        elif context.employment_trend == "improving":
            contributions["employment_trend"] = 0.5
            evidence.append("İstihdam eğilimi iyileşiyor")

        score = sum(contributions.values())

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
            feature_contributions={k: round(v, 4) for k, v in contributions.items()},
        ).recalculate()
