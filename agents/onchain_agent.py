"""OnChain Agent — zincir üstü verilerden yön çıkarır."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.onchain import OnChainContext


class OnChainAgent:
    def __init__(self):
        self.agent_id = "onchain_agent_v1"

    def analyze(self, context: OnChainContext) -> AgentOpinion:
        evidence = []
        caveats = []
        # Faz 268-sonrası: Feature Importance — bkz. agents/quant_agent.py
        # ve agents/technical_agent.py'deki aynı desen.
        contributions: dict[str, float] = {}

        # Exchange akışı
        if context.exchange_outflow_24h > context.exchange_inflow_24h * 1.5:
            contributions["exchange_flow"] = 1.5
            evidence.append("Güçlü borsa çıkışı — coin'ler borsalardan ayrılıyor")
        elif context.exchange_inflow_24h > context.exchange_outflow_24h * 1.5:
            contributions["exchange_flow"] = -1.5
            evidence.append("Güçlü borsa girişi — olası satış baskısı")

        # Balina aktivitesi — Faz 367-devam: kullanıcı onayıyla GEÇİCİ bir
        # yaklaşım (bkz. services/context_adapter.py::_real_onchain_metrics
        # ve onchain_provider.py::fetch_whale_like_exchange_flow) — gerçek
        # bireysel balina cüzdan takibi DEĞİL, tek bir borsadaki orantısız
        # yoğunlaşmış bakiye hareketinden türetilmiş bir tahmin. Evidence
        # metni bunu açıkça belirtiyor, kullanıcı gerçek bir balina
        # cüzdanı izlendiğini sanmasın diye.
        if context.whale_accumulation and context.whale_distribution:
            caveats.append("Çelişkili balina sinyalleri — aynı anda hem biriktirme hem dağıtım")
        elif context.whale_accumulation:
            contributions["whale_activity"] = 1.5
            evidence.append(
                "Balina benzeri biriktirme tespit edildi (borsa akışından türetilmiş yaklaşık sinyal, "
                "gerçek cüzdan takibi değil)"
            )
        elif context.whale_distribution:
            contributions["whale_activity"] = -1.5
            evidence.append(
                "Balina benzeri dağıtım tespit edildi (borsa akışından türetilmiş yaklaşık sinyal, "
                "gerçek cüzdan takibi değil)"
            )

        # Stablecoin arzı
        if context.stablecoin_mint_24h > 100_000_000:
            contributions["stablecoin_mint"] = 1.0
            evidence.append(f"Belirgin stablecoin basımı (${context.stablecoin_mint_24h:,.0f}) — olası alım gücü")

        # Uyuyan coin'ler
        if context.dormant_coins_moved:
            caveats.append("Uyuyan coin'ler hareket etti — olası piyasa anomalisi")

        # Faz 196: ETH gas fiyatı + Solana TPS — gerçek, kolay ölçülen ağ
        # aktivitesi metrikleri. Kasıtlı olarak yönü DEĞİŞTİRMİYOR (yüksek
        # gas'ın fiyat için bullish mi bearish mi olduğu literatürde net
        # değil) — sadece bağlam/uyarı notu olarak ekleniyor.
        if context.eth_gas_price_gwei is not None and context.eth_gas_price_gwei > 50:
            caveats.append(f"Yüksek ETH ağ tıkanıklığı (gas: {context.eth_gas_price_gwei:.1f} gwei)")
        if context.solana_tps is not None:
            # Faz 364-devam — kullanıcı bulgusu: piyasa sakinken (MVRV/NUPL/
            # SOPR nötr, hash_rate stable) bu satır TEK görünen evidence
            # olabiliyor ve yön puanına hiç katkısı olmadığı halde kararı
            # o belirliyormuş gibi yanıltıcı görünüyordu (bkz. yukarıdaki
            # skorlama — solana_tps için hiçbir contributions[] girişi yok).
            # Etiket ekleyerek bunu açıkça belirtiyoruz.
            evidence.append(f"Solana ağ aktivitesi: {context.solana_tps:.0f} tx/s (bilgi amaçlı, yön puanına katılmıyor)")

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
                contributions["network_activity_trend"] = 0.5
            evidence.append("Aktif adres sayısı artıyor — gerçek ağ kullanımı büyüyor (BTC)")
        elif context.network_activity_trend == "falling":
            if is_btc:
                contributions["network_activity_trend"] = -0.5
            evidence.append("Aktif adres sayısı azalıyor — ağ kullanımı düşüyor (BTC)")

        if context.hash_rate_trend == "falling":
            if is_btc:
                contributions["hash_rate_trend"] = -0.5
            evidence.append("Hash rate düşüyor — olası madenci kapitülasyonu (BTC)")
        elif context.hash_rate_trend == "rising":
            if is_btc:
                contributions["hash_rate_trend"] = 0.5
            evidence.append("Hash rate yükseliyor — madenci güveni/ağ güvenliği artıyor (BTC)")

        if not is_btc and context.network_activity_trend != "stable":
            caveats.append(
                f"BTC-{context.network_activity_trend} sinyali {context.symbol or 'bu sembol'} için bilgi "
                "amaçlı — yön puanına katılmadı (zincire özel bir eşdeğer henüz yok)"
            )

        # MVRV Z-Score
        if context.mvrv_zscore > 3.0:
            contributions["mvrv_zscore"] = -2.0
            evidence.append(f"MVRV Z-Score aşırı yüksek ({context.mvrv_zscore}) — piyasa aşırı değerli")
        elif context.mvrv_zscore < -1.0:
            contributions["mvrv_zscore"] = 2.0
            evidence.append(f"MVRV Z-Score aşırı düşük ({context.mvrv_zscore}) — piyasa aşırı ucuz")

        # Faz 335 — kullanıcı bulgusu: NUPL/SOPR fetch fonksiyonları
        # Faz 316-sonrası'nda yazılıp test edilmişti ama hiçbir ajana
        # bağlanmamıştı. MVRV Z-Score ile AYNI desen (genel piyasa
        # döngüsü göstergeleri, tüm kripto sembollerine uygulanıyor —
        # network_activity_trend/hash_rate_trend'in aksine BTC'ye
        # özel değiller).
        #
        # NUPL (Net Unrealized Profit/Loss): >0.75 "euphoria" (tarihsel
        # tepe bölgeleri, klasik on-chain rejim sınıflandırması), <0
        # "capitulation" (tarihsel dip bölgeleri).
        if context.nupl is not None:
            if context.nupl > 0.75:
                contributions["nupl"] = -1.5
                evidence.append(f"NUPL aşırı yüksek ({context.nupl:.2f}) — 'euphoria' bölgesi, tarihsel tepe riski")
            elif context.nupl < 0.0:
                contributions["nupl"] = 1.5
                evidence.append(f"NUPL negatif ({context.nupl:.2f}) — 'capitulation' bölgesi, tarihsel dip riski")

        # SOPR (Spent Output Profit Ratio): >1 ortalama kârla satış
        # (sağlıklı yükseliş devamı), <1 ortalama zararla satış
        # (kapitülasyon baskısı). ~1.0 civarı ("SOPR reset") kasıtlı
        # olarak puanlanmıyor — literatürde net/tutarlı bir yön
        # taşımıyor (hem destek hem direnç olarak yorumlanabiliyor),
        # sadece uç değerler (MVRV/NUPL ile AYNI "sadece aşırılık"
        # disiplini) puanlanıyor.
        if context.sopr is not None:
            if context.sopr < 0.98:
                contributions["sopr"] = -1.0
                evidence.append(f"SOPR düşük ({context.sopr:.3f}) — ortalama zararla satış, kapitülasyon baskısı")
            elif context.sopr > 1.05:
                contributions["sopr"] = 1.0
                evidence.append(f"SOPR yüksek ({context.sopr:.3f}) — ortalama kârla satış, sağlıklı yükseliş devamı")

        score = sum(contributions.values())

        # Faz 247: kritik bulgu — exchange_inflow/outflow, whale_accumulation/
        # distribution hâlâ hiç uygulanmıyor (Faz 196/215'in kasıtlı kararı:
        # dürüstçe ölçülemeyen bir şeyi icat etmemek — contracts/onchain.py'de
        # hep varsayılan/nötr kalıyorlar). mvrv_zscore Faz 268v'de gerçek
        # veriyle (bitcoin-data.com) beslenmeye başladı — bu skorlama zaten
        # Faz 196'dan beri buradaydı, sadece veri hiç gelmiyordu. Gerçek
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
            feature_contributions={k: round(v, 4) for k, v in contributions.items()},
        ).recalculate()
