"""Order Flow Agent — mikroyapı uzmanı. Gerçek order book verisiyle besleniyor
(Faz 186 — database/repositories/market_data_repository.py::
get_latest_order_book_snapshot)."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.order_flow import OrderFlowContext


class OrderFlowAgent:
    def __init__(self):
        self.agent_id = "order_flow_agent_v1"

    def analyze(self, context: OrderFlowContext) -> AgentOpinion:
        evidence = []
        caveats = []
        # Faz 268-sonrası: Feature Importance — bkz. agents/quant_agent.py
        # ve agents/technical_agent.py'deki aynı desen. Çarpımsal indirimler
        # (scale_all) O ANA KADAR birikmiş katkılara uygulanıyor — orijinal
        # `score *= X` sıralamasıyla birebir aynı.
        contributions: dict[str, float] = {}

        def scale_all(factor: float) -> None:
            for key in contributions:
                contributions[key] *= factor

        # Faz 411 — kullanıcı isteği: "gerçekten gürültü olduğunu tespit
        # ettiğimiz bütün sinyalleri mimariden temizleyelim." bid_ask_
        # imbalance, rejime göre ayrıştırılmış Feature IC denetiminde
        # HİÇBİR rejim segmentinde anlamlı çıkmadı (en yakını bearish_
        # normal'da p=0.317) — gerçekten gürültü. Kaldırıldı.

        # Agresif alış/satış oranı (taker flow)
        if context.aggressive_buy_ratio > 0.65:
            contributions["aggressive_buy_ratio"] = 1.0
            evidence.append(f"Agresif alış oranı {context.aggressive_buy_ratio:.2f} — taker-yönlü alım")
        elif context.aggressive_buy_ratio < 0.35:
            contributions["aggressive_buy_ratio"] = -1.0
            evidence.append(f"Agresif alış oranı {context.aggressive_buy_ratio:.2f} — taker-yönlü satım")

        # Geniş spread — düşük likidite, güveni azalt
        if context.spread_bps > 10:
            caveats.append(f"Geniş spread ({context.spread_bps:.1f} bps) — düşük likidite, azaltılmış güven")
            scale_all(0.5)
        elif context.spread_bps == 0:
            caveats.append("Spread verisi mevcut değil")

        # Faz 411 — kullanıcı isteği: "gerçekten gürültü olduğunu tespit
        # ettiğimiz bütün sinyalleri mimariden temizleyelim." funding_rate,
        # rejime göre ayrıştırılmış Feature IC denetiminde hiçbir rejim
        # segmentinde anlamlı çıkmadı (overall p=0.97, n=211 — zaten çok
        # zayıf) — gerçekten gürültü. Kaldırıldı.

        # Open interest trend — technical_agent'taki ADX'in rolüyle aynı
        # desen: yön belirlemiyor, mevcut yönü (yukarıdaki imbalance/
        # taker akışından gelen) teyit ediyor ya da güveni azaltıyor.
        current_score = sum(contributions.values())
        if context.open_interest_trend == "rising" and current_score != 0:
            contributions["open_interest_confirm"] = 0.3 if current_score > 0 else -0.3
            evidence.append("Açık pozisyon (open interest) artıyor — yeni para yönü teyit ediyor")
        elif context.open_interest_trend == "falling":
            caveats.append("Açık pozisyon (open interest) azalıyor — pozisyon kapatma, azaltılmış güven")
            scale_all(0.85)

        score = sum(contributions.values())

        if score > 0.5:
            direction = "LONG"
        elif score < -0.5:
            direction = "SHORT"
        else:
            direction = "WAIT"

        confidence = min(abs(score) / 3.5, 0.8)

        return AgentOpinion(
            agent_id=self.agent_id,
            domain=AgentDomain.ORDER_FLOW,
            direction=direction,
            confidence=round(confidence, 3),
            evidence_strength=0.7,
            data_quality=0.8,
            freshness=0.95,  # order book near-real-time
            source_reliability=0.8,
            evidence=evidence,
            caveats=caveats,
            feature_contributions={k: round(v, 4) for k, v in contributions.items()},
        ).recalculate()
