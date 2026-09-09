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
        # Faz 412 — kullanıcı isteği: "bizzat ajanlarda gürültü yapıyor
        # olabilir onları da kontrol edelim." Domain-seviyesi denetimde
        # order_flow'un bullish_low rejiminde net ZARARLI olduğu bulundu
        # (ablation: pivotal olduğu 22 kararda toplam -4248$, işlem başına
        # -193$ beklenti; yönlü IC: p=0,014 anlamlı negatif) — ama TEK TEK
        # feature'lar (aggressive_buy_ratio kendi başına p=0,18) wyckoff_
        # event/structure_phase'in (Faz 411, p<0,001) geçtiği çıtayı
        # geçmiyor. Kök neden muhtemelen open_interest_confirm'ün zayıf/
        # belirsiz bir sinyali güçlendirmesi — o yüzden TEK bir feature
        # değil, TÜM domain bullish_low'da gölgeleniyor (skora sıfır
        # etki, feature_ic ile izlemeye devam).
        shadow_contributions: dict[str, float] = {}
        is_shadow_regime = context.market_regime == "bullish_low"

        def scale_all(factor: float) -> None:
            for key in contributions:
                contributions[key] *= factor

        def _place(key: str, raw_value: float, evidence_text: str) -> None:
            if is_shadow_regime:
                shadow_contributions[key] = raw_value
                evidence.append(f"{evidence_text} (bullish_low rejiminde zararlı bulundu — ağırlığı sıfır, izleniyor)")
            else:
                contributions[key] = raw_value
                evidence.append(evidence_text)

        # Faz 411 — bid_ask_imbalance, rejime göre ayrıştırılmış Feature IC
        # denetiminde HİÇBİR rejim segmentinde anlamlı çıkmadı — kaldırıldı.

        # Agresif alış/satış oranı (taker flow)
        if context.aggressive_buy_ratio > 0.65:
            _place("aggressive_buy_ratio", 1.0, f"Agresif alış oranı {context.aggressive_buy_ratio:.2f} — taker-yönlü alım")
        elif context.aggressive_buy_ratio < 0.35:
            _place("aggressive_buy_ratio", -1.0, f"Agresif alış oranı {context.aggressive_buy_ratio:.2f} — taker-yönlü satım")

        # Geniş spread — düşük likidite, güveni azalt
        if context.spread_bps > 10:
            caveats.append(f"Geniş spread ({context.spread_bps:.1f} bps) — düşük likidite, azaltılmış güven")
            scale_all(0.5)
        elif context.spread_bps == 0:
            caveats.append("Spread verisi mevcut değil")

        # Faz 411 — funding_rate, rejime göre ayrıştırılmış Feature IC
        # denetiminde hiçbir rejim segmentinde anlamlı çıkmadı — kaldırıldı.

        # Open interest trend — technical_agent'taki ADX'in rolüyle aynı
        # desen: yön belirlemiyor, mevcut yönü (yukarıdaki imbalance/
        # taker akışından gelen) teyit ediyor ya da güveni azaltıyor.
        # Faz 412: bullish_low'da referans skor GERÇEK contributions değil
        # shadow_contributions'tan alınıyor — o rejimde aggressive_buy_
        # ratio zaten shadow'da, gerçek skor hep 0 olurdu ve bu blok hiç
        # tetiklenmezdi; shadow'daki yönü referans alarak feature_ic'in
        # izlemeye devam edebilmesi sağlanıyor.
        reference_score = sum(shadow_contributions.values()) if is_shadow_regime else sum(contributions.values())
        if context.open_interest_trend == "rising" and reference_score != 0:
            _place(
                "open_interest_confirm", 0.3 if reference_score > 0 else -0.3,
                "Açık pozisyon (open interest) artıyor — yeni para yönü teyit ediyor",
            )
        elif context.open_interest_trend == "falling":
            caveats.append("Açık pozisyon (open interest) azalıyor — pozisyon kapatma, azaltılmış güven")
            scale_all(0.85)

        # Faz 464 (2026-09-09) — kullanıcı kararı: "Önce kanıtlanmış
        # özellikleri bağlayalım." Faz 436'nın fiyat/OI/funding ÜÇLÜSÜNÜ
        # tek kategoriye ayıran sinyali bir yıl önce "önce gözlemle,
        # kanıtlanırsa wire et" diye eklenmiş, `ctx.market.features`'ta
        # akmış ama HİÇ ölçülmemişti. Faz 462/463'te ölçüldü ve DÖRT kanıt
        # şartını birden geçen TEK yeni özellik oldu:
        #   anlamlı ayrım (+0,167 ham) + günlük tutarlılık (6/6 gün) +
        #   sembol-içi ayrım (+0,030, aynı işaretli) + piyasa-geneli DEĞİL.
        #
        # GERÇEK ÖLÇÜLEN P(1 saat sonra YUKARI), n=7.729:
        #   bullish_short_covering      0,369   <- EN DÜŞÜK
        #   bullish_new_longs           0,400
        #   bearish_new_shorts          0,430
        #   unclear                     0,474   (taban)
        #   bearish_long_capitulation   0,533   <- EN YÜKSEK
        #
        # Yani "bullish" kategoriler DÜŞÜŞ, "long kapitülasyonu" YÜKSELİŞ
        # habercisi — Faz 460/463'ün genel ortalamaya-dönüş örüntüsüyle
        # birebir aynı. Katsayılar bu ölçülen sıralamadan türetildi
        # (taban 0,474'e göre sapma x2), İCAT EDİLMEDİ. Büyüklükler
        # KASITLI olarak küçük: sembol-içi gerçek edge ~3 puan, ham
        # +0,167 değil — abartılı bir ağırlık ölçümün desteklediğinden
        # fazlasını iddia ederdi.
        _RELATIONSHIP_SCORES = {
            "bullish_short_covering": -0.6,
            "bullish_new_longs": -0.4,
            "bearish_new_shorts": -0.2,
            "bearish_long_capitulation": +0.3,
        }
        relationship = context.order_flow_relationship_category
        if relationship in _RELATIONSHIP_SCORES:
            _place(
                "order_flow_relationship", _RELATIONSHIP_SCORES[relationship],
                f"Fiyat/OI/funding ilişkisi: {relationship} — ölçülen 1sa yön eğilimi "
                f"({'düşüş' if _RELATIONSHIP_SCORES[relationship] < 0 else 'yükseliş'})",
            )
        elif relationship == "unclear":
            # Ölçülen P(UP)=0,474 taban değerin kendisi -- bilgi taşımıyor,
            # skora 0 katkı (uydurma bir yön verilmiyor).
            caveats.append("Fiyat/OI/funding ilişkisi belirsiz — yön bilgisi yok")

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
            feature_contributions={k: round(v, 4) for k, v in {**shadow_contributions, **contributions}.items()},
        ).recalculate()
