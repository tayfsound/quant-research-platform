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

        # Likidite — Faz 215: gerçek bulgu — sadece "tight" cezalandırılıyordu,
        # "loose" (genişleyen M2 para arzı — tarihsel olarak risk
        # varlıkları için destekleyici) hiç ödüllendirilmiyordu. Asimetrik:
        # ajan likiditenin sadece kötü tarafını görebiliyordu.
        #
        # Faz 408 — kullanıcı isteği (2026-09-03, ölçüm stabilitesi
        # araştırması sırasında bulundu): macro'nun raw_confidence'ı 1812
        # gerçek karardan HİÇBİRİNDE farklı çıkmıyordu — hep tam 0.167.
        # Kök neden bug DEĞİL (FRED_API_KEY çalışıyor, veriler gerçek/
        # güncel) — GERÇEK bir tasarım zayıflığı: liquidity_condition
        # (M2SL, ±1.0) ile net_liquidity_trend (aşağıda, ±1.0) son ~1 aydır
        # sürekli TERS yönde çıkıyor (M2SL "loose" +1.0, net likidite
        # "contracting" -1.0) ve toplamda birbirini TAM götürüyor — geriye
        # sadece employment_trend'in ±0.5'i kalıyor, confidence hep
        # 0.5/3.0=0.167'de donuyor. İkisi FARKLI şeyler ölçüyor (M2SL geniş/
        # yavaş para arzı, net likidite Fed'in hızlı/güncel operasyonları)
        # — Faz 267'nin kendi gerekçesi net_liquidity_trend'in DAHA
        # GÜNCEL/İLGİLİ sinyal olduğunu söylüyor, bu yüzden artık BASKIN
        # (±1.0) o, liquidity_condition (M2SL) ise YAVAŞ ONAYLAYICI bir
        # ikincil sinyal (±0.5) — ikisi çatıştığında net likidite ağır
        # basıyor, tam iptal yerine.
        if context.liquidity_condition == "tight":
            contributions["liquidity_condition"] = -0.5
            evidence.append("Likidite koşulları kısıtlayıcı")
        elif context.liquidity_condition == "loose":
            contributions["liquidity_condition"] = 0.5
            evidence.append("Likidite koşulları genişletici")

        # Faz 267 — kullanıcı bulgusu: "devletler borçlarını dört yıllık
        # dönemlerle öder, bu döngü tamamlanınca piyasaya likidite girer."
        # liquidity_condition (yukarıda, M2SL) bunu yakalayamıyor — aylık,
        # yavaş. net_liquidity_trend (Fed bilançosu - Hazine nakit hesabı
        # - ters repo) haftalık/günlük, çok daha hızlı. Boş string ("veri
        # yok", API/key eksikse) hiçbir puan vermiyor — icat edilmiş bir
        # nötr varsayım değil. Faz 408 — artık BASKIN likidite sinyali
        # (±1.0, yukarıdaki not) — daha hızlı/güncel olduğu için
        # liquidity_condition'la çatıştığında ağır basıyor.
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
