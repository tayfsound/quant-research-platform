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
        # Faz 302 — kullanıcı isteği: dış rapor + analytics/feature_ic.py'nin
        # gerçek veriyle doğrulanmış bulgusu: structure_phase (IC=-0.392,
        # n=155, p≈0.0000) ve wyckoff_event (IC=-0.4464, n=83, p≈0.0000) —
        # her iki yarıda (kronolojik split) da tutarlı, 25-29 farklı sembolde
        # — bu sistemin gerçek verisinde TERS yönde çalışıyor (klasik Wyckoff
        # teorisinin varsaydığının tersi). Kod tarafında işaret hatası YOK
        # (accumulation/spring=bullish, distribution/upthrust=bearish —
        # ders kitabı doğru), yani bu gerçek bir ampirik bulgu.
        # Örneklem sadece 5 günlük tek bir pencereye sıkışık olduğu için
        # (rejim çeşitliliği doğrulanmadı) işareti TERSİNE ÇEVİRMEK yerine
        # şimdilik skora katkısını SIFIRLIYORUZ (daha güvenli, tersine
        # çevrilebilir) — ama feature_ic'in izlemeye devam edebilmesi için
        # gerçek (sıfırlanmamış) değerleri shadow_contributions'a yazıyoruz.
        # Birkaç hafta/farklı rejimde ters yön kalıcı çıkarsa işareti
        # çevirmek ayrı, sonraki bir karar olacak.
        shadow_contributions: dict[str, float] = {}

        def scale_all(factor: float) -> None:
            for key in contributions:
                contributions[key] *= factor

        # Wyckoff fazı — skora katkısı sıfırlandı (bkz. yukarıdaki not),
        # sadece izleme için shadow_contributions'a yazılıyor.
        if context.structure_phase == "accumulation":
            shadow_contributions["structure_phase"] = 1.5
            evidence.append("Wyckoff birikim (accumulation) fazı tespit edildi (ağırlığı ampirik ters IC nedeniyle sıfırlandı, izleniyor)")
        elif context.structure_phase == "distribution":
            shadow_contributions["structure_phase"] = -1.5
            evidence.append("Wyckoff dağıtım (distribution) fazı tespit edildi (ağırlığı ampirik ters IC nedeniyle sıfırlandı, izleniyor)")
        elif context.structure_phase == "markup":
            shadow_contributions["structure_phase"] = 1.0
            evidence.append("Markup fazı tespit edildi (ağırlığı ampirik ters IC nedeniyle sıfırlandı, izleniyor)")
        elif context.structure_phase == "markdown":
            shadow_contributions["structure_phase"] = -1.0
            evidence.append("Markdown fazı tespit edildi (ağırlığı ampirik ters IC nedeniyle sıfırlandı, izleniyor)")

        # Faz 237: gerçek, kesin tanımlı Wyckoff olayları — skora katkısı
        # sıfırlandı (bkz. yukarıdaki not), sadece izleme için
        # shadow_contributions'a yazılıyor.
        if context.wyckoff_event == "spring":
            shadow_contributions["wyckoff_event"] = 2.0
            evidence.append("Wyckoff spring tespit edildi (ağırlığı ampirik ters IC nedeniyle sıfırlandı, izleniyor)")
        elif context.wyckoff_event == "upthrust":
            shadow_contributions["wyckoff_event"] = -2.0
            evidence.append("Wyckoff upthrust tespit edildi (ağırlığı ampirik ters IC nedeniyle sıfırlandı, izleniyor)")
        elif context.wyckoff_event == "sign_of_strength":
            shadow_contributions["wyckoff_event"] = 1.5
            evidence.append("Wyckoff sign of strength tespit edildi (ağırlığı ampirik ters IC nedeniyle sıfırlandı, izleniyor)")
        elif context.wyckoff_event == "sign_of_weakness":
            shadow_contributions["wyckoff_event"] = -1.5
            evidence.append("Wyckoff sign of weakness tespit edildi (ağırlığı ampirik ters IC nedeniyle sıfırlandı, izleniyor)")

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

        # Likidite süpürme — genellikle ters yönlü bir hareketin habercisi
        if context.liquidity_sweep == "buy_side_swept":
            contributions["liquidity_sweep"] = -0.5
            evidence.append("Alış-yönü likiditesi süpürüldü — olası aşağı dönüş")
        elif context.liquidity_sweep == "sell_side_swept":
            contributions["liquidity_sweep"] = 0.5
            evidence.append("Satış-yönü likiditesi süpürüldü — olası yukarı dönüş")

        # Faz 223: klasik Fibonacci retracement — destek/dirençte olmak
        # tek başına yön belirlemez (fiyat bir seviyeden dönebilir de
        # kırıp geçebilir de), bu yüzden mevcut yapısal kanıtı (BOS/swing)
        # DOĞRULAYAN yönde hafifçe güçlendiriyor, kendi başına yeni bir
        # yön açmıyor.
        current_score = sum(contributions.values())
        if context.fibonacci_price_position == "at_support":
            if current_score > 0:
                contributions["fibonacci_confirm"] = 0.5
                evidence.append(f"Fiyat Fibonacci desteğinde ({context.fibonacci_nearest_level}) — yükseliş yapısını teyit ediyor")
            else:
                caveats.append(f"Fiyat Fibonacci desteğinde ({context.fibonacci_nearest_level}) ama yapı düşüş yönlü — karışık sinyal")
        elif context.fibonacci_price_position == "at_resistance":
            if current_score < 0:
                contributions["fibonacci_confirm"] = -0.5
                evidence.append(f"Fiyat Fibonacci direncinde ({context.fibonacci_nearest_level}) — düşüş yapısını teyit ediyor")
            else:
                caveats.append(f"Fiyat Fibonacci direncinde ({context.fibonacci_nearest_level}) ama yapı yükseliş yönlü — karışık sinyal")

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
