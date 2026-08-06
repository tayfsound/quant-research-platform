"""OnChain Agent — zincir üstü verilerden yön çıkarır."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.onchain import OnChainContext


class OnChainAgent:
    def __init__(self):
        self.agent_id = "onchain_agent_v1"

    def analyze(self, context: OnChainContext) -> AgentOpinion:
        evidence = []
        caveats = []
        score = 0.0

        # Exchange akışı
        if context.exchange_outflow_24h > context.exchange_inflow_24h * 1.5:
            score += 1.5
            evidence.append("Strong exchange outflow — coins leaving exchanges")
        elif context.exchange_inflow_24h > context.exchange_outflow_24h * 1.5:
            score -= 1.5
            evidence.append("Strong exchange inflow — potential selling pressure")

        # Balina aktivitesi
        if context.whale_accumulation and context.whale_distribution:
            caveats.append("Conflicting whale signals detected — accumulation and distribution simultaneously")
        elif context.whale_accumulation:
            score += 1.5
            evidence.append("Whale accumulation detected")
        elif context.whale_distribution:
            score -= 1.5
            evidence.append("Whale distribution detected")

        # Stablecoin arzı
        if context.stablecoin_mint_24h > 100_000_000:
            score += 1.0
            evidence.append(f"Significant stablecoin minting (${context.stablecoin_mint_24h:,.0f}) — potential buying power")

        # Uyuyan coin'ler
        if context.dormant_coins_moved:
            caveats.append("Dormant coins moved — potential market anomaly")

        # Faz 196: ETH gas fiyatı + Solana TPS — gerçek, kolay ölçülen ağ
        # aktivitesi metrikleri. Kasıtlı olarak yönü DEĞİŞTİRMİYOR (yüksek
        # gas'ın fiyat için bullish mi bearish mi olduğu literatürde net
        # değil) — sadece bağlam/uyarı notu olarak ekleniyor.
        if context.eth_gas_price_gwei is not None and context.eth_gas_price_gwei > 50:
            caveats.append(f"High ETH network congestion (gas: {context.eth_gas_price_gwei:.1f} gwei)")
        if context.solana_tps is not None:
            evidence.append(f"Solana network activity: {context.solana_tps:.0f} tx/s")

        # Faz 215: gerçek ağ kullanım/madenci trendleri (blockchain.info,
        # Bitcoin'e özel). Aktif adres artışı = gerçek kullanım büyüyor
        # (hafif bullish). Hash rate düşüşü tarihsel olarak madenci
        # kapitülasyonuyla ilişkilendirilir (hafif bearish); artışı
        # madenci güveni/ağ güvenliği artıyor demek (hafif bullish).
        if context.network_activity_trend == "rising":
            score += 0.5
            evidence.append("Active address count rising — real network usage growing")
        elif context.network_activity_trend == "falling":
            score -= 0.5
            evidence.append("Active address count falling — network usage declining")

        if context.hash_rate_trend == "falling":
            score -= 0.5
            evidence.append("Hash rate declining — possible miner capitulation")
        elif context.hash_rate_trend == "rising":
            score += 0.5
            evidence.append("Hash rate rising — miner conviction/network security increasing")

        # MVRV Z-Score
        if context.mvrv_zscore > 3.0:
            score -= 2.0
            evidence.append(f"MVRV Z-Score extremely high ({context.mvrv_zscore}) — market overvalued")
        elif context.mvrv_zscore < -1.0:
            score += 2.0
            evidence.append(f"MVRV Z-Score extremely low ({context.mvrv_zscore}) — market undervalued")

        if score > 0.5:
            direction = "LONG"
        elif score < -0.5:
            direction = "SHORT"
        else:
            direction = "WAIT"

        confidence = min(abs(score) / 5.0, 0.85)

        return AgentOpinion(
            agent_id=self.agent_id,
            domain=AgentDomain.ONCHAIN,
            direction=direction,
            confidence=round(confidence, 3),
            evidence_strength=0.75,
            data_quality=0.80,
            freshness=0.70,
            source_reliability=0.85,
            evidence=evidence,
            caveats=caveats,
        ).recalculate()
