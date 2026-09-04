"""Pattern Agent — Wyckoff/Elliott/market structure uzmanı."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.pattern import PatternContext


class PatternAgent:
    def __init__(self):
        self.agent_id = "pattern_agent_v1"

    def analyze(self, context: PatternContext) -> AgentOpinion:
        evidence = []
        caveats = []
        # Faz 268-sonrası: Feature Importance — bkz. agents/quant_agent.py
        # ve agents/technical_agent.py'deki aynı desen. scale_all, O ANA
        # KADAR birikmiş katkılara uygulanıyor — orijinal `score *= X`
        # sıralamasıyla birebir aynı.
        contributions: dict[str, float] = {}
        # Faz 302 — dış rapor + feature_ic.py'nin TOPLU (rejim ayrımı
        # olmadan) bulgusu: structure_phase/wyckoff_event ters yönde
        # çalışıyor göründü, güvenli olduğu için skora katkısı sıfırlanıp
        # SADECE shadow_contributions'a yazıldı (izleme, sıfır etki).
        #
        # Faz 411 — kullanıcı isteği (2026-09-04, "gürültü sinyalleri"
        # denetimi): rejime göre ayrıştırınca TOPLU "gürültü" görüntüsünün
        # aslında İKİ rejimde ZIT işaretli ama HER İKİSİ DE gerçek/anlamlı
        # sinyalin birbirini iptal etmesinden kaynaklandığı bulundu:
        #   wyckoff_event: bullish_low'da IC=+0.296 (p=0.003, n=96, doğru
        #     yönde) — bearish_low'da IC=-0.270 (p=0.0002, n=183, TERS
        #     yönde). structure_phase: bearish_low'da IC=-0.2515 (p≈0,
        #     n=334, çok güçlü, TERS yönde) — diğer rejimlerde anlamsız/
        #     yetersiz örneklem.
        # Artık SADECE bu kanıtlanmış rejimlerde gerçek katkı veriyor
        # (bearish_low'da işaret TERSİNE çevrilerek — kanıt o yönde),
        # kanıtsız rejimlerde hâlâ shadow'da (sıfır etki, izlemeye devam).
        shadow_contributions: dict[str, float] = {}

        def scale_all(factor: float) -> None:
            for key in contributions:
                contributions[key] *= factor

        def _regime_gated(raw_value: float, key: str, evidence_text: str, positive_regime: str | None, inverted_regime: str | None) -> None:
            if positive_regime is not None and context.market_regime == positive_regime:
                contributions[key] = raw_value
                evidence.append(f"{evidence_text} ({positive_regime} rejiminde ampirik olarak doğrulanmış yön)")
            elif inverted_regime is not None and context.market_regime == inverted_regime:
                contributions[key] = -raw_value
                evidence.append(f"{evidence_text} ({inverted_regime} rejiminde ampirik olarak TERS yönde doğrulanmış — işaret çevrildi)")
            else:
                shadow_contributions[key] = raw_value
                evidence.append(f"{evidence_text} (bu rejimde henüz kanıtlanmamış, ağırlığı sıfır, izleniyor)")

        # Wyckoff fazı — bkz. yukarıdaki Faz 411 notu.
        if context.structure_phase == "accumulation":
            _regime_gated(1.5, "structure_phase", "Wyckoff birikim (accumulation) fazı tespit edildi", None, "bearish_low")
        elif context.structure_phase == "distribution":
            _regime_gated(-1.5, "structure_phase", "Wyckoff dağıtım (distribution) fazı tespit edildi", None, "bearish_low")
        elif context.structure_phase == "markup":
            _regime_gated(1.0, "structure_phase", "Markup fazı tespit edildi", None, "bearish_low")
        elif context.structure_phase == "markdown":
            _regime_gated(-1.0, "structure_phase", "Markdown fazı tespit edildi", None, "bearish_low")

        # Faz 237: gerçek, kesin tanımlı Wyckoff olayları — bkz. yukarıdaki
        # Faz 411 notu.
        if context.wyckoff_event == "spring":
            _regime_gated(2.0, "wyckoff_event", "Wyckoff spring tespit edildi", "bullish_low", "bearish_low")
        elif context.wyckoff_event == "upthrust":
            _regime_gated(-2.0, "wyckoff_event", "Wyckoff upthrust tespit edildi", "bullish_low", "bearish_low")
        elif context.wyckoff_event == "sign_of_strength":
            _regime_gated(1.5, "wyckoff_event", "Wyckoff sign of strength tespit edildi", "bullish_low", "bearish_low")
        elif context.wyckoff_event == "sign_of_weakness":
            _regime_gated(-1.5, "wyckoff_event", "Wyckoff sign of weakness tespit edildi", "bullish_low", "bearish_low")

        # Break of Structure
        if context.break_of_structure == "bullish":
            contributions["break_of_structure"] = 1.5
            evidence.append("Yükseliş yönlü yapı kırılımı (BOS)")
        elif context.break_of_structure == "bearish":
            contributions["break_of_structure"] = -1.5
            evidence.append("Düşüş yönlü yapı kırılımı (BOS)")

        # Change of Character — trend güvenini azaltır
        if context.change_of_character:
            caveats.append("Karakter değişimi (CHoCH) tespit edildi — trend dönüş riski")
            scale_all(0.6)

        # Fair Value Gap
        if context.fair_value_gap == "bullish":
            contributions["fair_value_gap"] = 0.5
            evidence.append("Yükseliş yönlü adil değer boşluğu (FVG) doldurulmamış")
        elif context.fair_value_gap == "bearish":
            contributions["fair_value_gap"] = -0.5
            evidence.append("Düşüş yönlü adil değer boşluğu (FVG) doldurulmamış")

        # Swing structure
        if context.swing_structure == "higher_highs_higher_lows":
            contributions["swing_structure"] = 1.0
            evidence.append("Yükselen tepeler / yükselen dipler — yükseliş yönlü salınım yapısı")
        elif context.swing_structure == "lower_highs_lower_lows":
            contributions["swing_structure"] = -1.0
            evidence.append("Alçalan tepeler / alçalan dipler — düşüş yönlü salınım yapısı")
        else:
            caveats.append("Karışık salınım yapısı — net bir yön eğilimi yok")

        # Faz 411 — kullanıcı isteği: "gerçekten gürültü olduğunu tespit
        # ettiğimiz bütün sinyalleri mimariden temizleyelim." liquidity_sweep
        # ve fibonacci_confirm, rejime göre ayrıştırılmış Feature IC
        # denetiminde HİÇBİR rejim segmentinde anlamlı çıkmadı (en yakını
        # liquidity_sweep'in bullish_high'da p=0.062, fibonacci_confirm'in
        # bullish_normal'da p=0.083 — ikisi de eşiği geçemedi) — gerçekten
        # gürültü, wyckoff_event/structure_phase'in aksine (onlarda rejime
        # göre gerçek sinyal bulunmuştu). Kaldırıldı, skora hiç katkı
        # vermiyor artık.

        # Faz 268-sonrası — kullanıcı isteği: "fiyatın akümüle olduğu
        # bölgelere göre strateji" — gerçek Volume Profile (bkz.
        # signal_engine.compute_volume_profile). Fibonacci ile AYNI ilke:
        # yüksek-hacim bölgesi (gerçek biriktirme/support-resistance)
        # kendi başına yön açmıyor, mevcut yapısal kanıtı DOĞRULUYOR.
        current_score = sum(contributions.values())
        if context.near_high_volume_node:
            if current_score > 0:
                contributions["volume_profile_confirm"] = 0.5
                evidence.append("Fiyat yüksek hacimli bir birikim bölgesine yakın — yükseliş yapısını teyit ediyor (gerçek destek)")
            elif current_score < 0:
                contributions["volume_profile_confirm"] = -0.5
                evidence.append("Fiyat yüksek hacimli bir birikim bölgesine yakın — düşüş yapısını teyit ediyor (gerçek direnç)")
        if not context.in_value_area:
            caveats.append("Fiyat hacim-profili değer alanının (son hacmin ~%70'i) dışında — burada likidite daha ince")

        score = sum(contributions.values())

        if score > 0.5:
            direction = "LONG"
        elif score < -0.5:
            direction = "SHORT"
        else:
            direction = "WAIT"

        confidence = min(abs(score) / 5.0, 0.85)

        return AgentOpinion(
            agent_id=self.agent_id,
            domain=AgentDomain.PATTERN,
            direction=direction,
            confidence=round(confidence, 3),
            evidence_strength=0.65,
            data_quality=0.75,
            freshness=0.85,
            source_reliability=0.7,
            evidence=evidence,
            caveats=caveats,
            feature_contributions={k: round(v, 4) for k, v in {**shadow_contributions, **contributions}.items()},
        ).recalculate()
