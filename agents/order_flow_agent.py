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
        score = 0.0

        # Bid/Ask dengesizliği
        if context.bid_ask_imbalance > 0.3:
            score += 1.5
            evidence.append(f"Bid-side imbalance {context.bid_ask_imbalance:.2f} — buying pressure")
        elif context.bid_ask_imbalance < -0.3:
            score -= 1.5
            evidence.append(f"Ask-side imbalance {context.bid_ask_imbalance:.2f} — selling pressure")

        # Agresif alış/satış oranı (taker flow)
        if context.aggressive_buy_ratio > 0.65:
            score += 1.0
            evidence.append(f"Aggressive buy ratio {context.aggressive_buy_ratio:.2f} — taker-driven buying")
        elif context.aggressive_buy_ratio < 0.35:
            score -= 1.0
            evidence.append(f"Aggressive buy ratio {context.aggressive_buy_ratio:.2f} — taker-driven selling")

        # Geniş spread — düşük likidite, güveni azalt
        if context.spread_bps > 10:
            caveats.append(f"Wide spread ({context.spread_bps:.1f} bps) — low liquidity, reduced conviction")
            score *= 0.5
        elif context.spread_bps == 0:
            caveats.append("No spread data available")

        # Faz 247-249: funding rate — sentiment_agent'ın positioning
        # yorumuyla AYNI kontrarian felsefe (market_data/sentiment/
        # positioning_provider.py). Kalabalık pozisyonlanma (aşırı pozitif
        # funding = long'lar sıkışık) bir onay değil, bir uyarı — eşikler
        # Binance'in normal 8 saatlik funding aralığına (~±0.01%) göre,
        # >0.05% endüstri genelinde "yüksek" kabul edilir.
        if context.funding_rate is not None:
            if context.funding_rate > 0.0005:
                score -= 0.6
                evidence.append(f"Funding rate {context.funding_rate:.4%} — crowded long positioning (contrarian)")
            elif context.funding_rate < -0.0005:
                score += 0.6
                evidence.append(f"Funding rate {context.funding_rate:.4%} — crowded short positioning (contrarian)")

        # Open interest trend — technical_agent'taki ADX'in rolüyle aynı
        # desen: yön belirlemiyor, mevcut yönü (yukarıdaki imbalance/
        # taker akışından gelen) teyit ediyor ya da güveni azaltıyor.
        if context.open_interest_trend == "rising" and score != 0:
            score += 0.3 if score > 0 else -0.3
            evidence.append("Open interest rising — new money confirming direction")
        elif context.open_interest_trend == "falling":
            caveats.append("Open interest falling — position unwinding, reduced conviction")
            score *= 0.85

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
        ).recalculate()
