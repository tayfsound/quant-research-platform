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
        #
        # Faz 248: kritik bulgu — bu iki metrik SADECE Bitcoin zincirinden
        # geliyor ama önceden TÜM sembollere (ETHUSDT, SOLUSDT dahil) aynen
        # yön puanına uygulanıyordu — ETH/SOL işlem alırken aslında BTC'nin
        # ağ sağlığına göre karar veriliyordu. Artık SADECE gerçekten BTC
        # işlem görürken yön puanına katkı sağlıyor; diğer sembollerde
        # (ETH/SOL'a özel bir eşdeğer henüz yok — bkz. contracts/onchain.py
        # üstteki not) sadece bilgi notu (evidence) olarak kalıyor, eth_gas_
        # price_gwei/solana_tps ile AYNI kasıtlı sınırlama.
        is_btc = context.symbol.upper().startswith("BTC")

        if context.network_activity_trend == "rising":
            if is_btc:
                score += 0.5
            evidence.append("Active address count rising — real network usage growing (BTC)")
        elif context.network_activity_trend == "falling":
            if is_btc:
                score -= 0.5
            evidence.append("Active address count falling — network usage declining (BTC)")

        if context.hash_rate_trend == "falling":
            if is_btc:
                score -= 0.5
            evidence.append("Hash rate declining — possible miner capitulation (BTC)")
        elif context.hash_rate_trend == "rising":
            if is_btc:
                score += 0.5
            evidence.append("Hash rate rising — miner conviction/network security increasing (BTC)")

        if not is_btc and context.network_activity_trend != "stable":
            caveats.append(
                f"BTC-{context.network_activity_trend} sinyali {context.symbol or 'bu sembol'} için bilgi "
                "amaçlı — yön puanına katılmadı (zincire özel bir eşdeğer henüz yok)"
            )

        # MVRV Z-Score
        if context.mvrv_zscore > 3.0:
            score -= 2.0
            evidence.append(f"MVRV Z-Score extremely high ({context.mvrv_zscore}) — market overvalued")
        elif context.mvrv_zscore < -1.0:
            score += 2.0
            evidence.append(f"MVRV Z-Score extremely low ({context.mvrv_zscore}) — market undervalued")

        # Faz 247: kritik bulgu — exchange_inflow/outflow, whale_accumulation/
        # distribution, mvrv_zscore hâlâ hiç uygulanmadı (Faz 196/215'in
        # kasıtlı kararı: dürüstçe ölçülemeyen bir şeyi icat etmemek —
        # contracts/onchain.py'de hep varsayılan/nötr kalıyorlar). Gerçek
        # veride bu ajan 4.678 kayıtta TEK BİR KEZ bile yönlü oy vermemiş,
        # çünkü eşik (>0.5) SADECE bu hiç-tetiklenmeyen sinyaller devredeyken
        # anlamlıydı — GERÇEKTEN çalışan iki sinyal (network_activity_trend,
        # hash_rate_trend) tek başına ±0.5 veriyor, ki >0.5 eşiğini asla
        # AŞAMIYOR (eşit, büyük değil). Sonuç: onchain ajanı elindeki gerçek
        # bilgiyi (Bitcoin ağ sağlığı trendleri) hiçbir zaman ifade
        # edemiyordu. Eşik 0.4'e çekildi — tek bir gerçek trend sinyali
        # artık (düşük konviksiyonla, confidence=0.1) bir görüş
        # bildirebiliyor; iki trend aynı yönde ya da mint/mvrv gibi daha
        # güçlü sinyallerle birleştiğinde konviksiyon zaten doğal olarak
        # artıyor (confidence = |score|/5).
        if score > 0.4:
            direction = "LONG"
        elif score < -0.4:
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
