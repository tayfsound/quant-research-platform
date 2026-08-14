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

        def scale_all(factor: float) -> None:
            for key in contributions:
                contributions[key] *= factor

        # Wyckoff fazı
        if context.structure_phase == "accumulation":
            contributions["structure_phase"] = 1.5
            evidence.append("Wyckoff accumulation phase detected")
        elif context.structure_phase == "distribution":
            contributions["structure_phase"] = -1.5
            evidence.append("Wyckoff distribution phase detected")
        elif context.structure_phase == "markup":
            contributions["structure_phase"] = 1.0
            evidence.append("Markup phase — trend continuation likely")
        elif context.structure_phase == "markdown":
            contributions["structure_phase"] = -1.0
            evidence.append("Markdown phase — trend continuation likely")

        # Faz 237: gerçek, kesin tanımlı Wyckoff olayları — structure_phase
        # (yukarıda) kaba bir genel-rejim yaklaşıklaması, bunlar ise ayrık,
        # net kurallarla tespit edilen olaylar (bkz. signal_engine.py::
        # _wyckoff_event). Spring/SOS en güçlü, en klasik Wyckoff sinyalleri
        # olduğu için structure_phase'ten daha yüksek ağırlıklı.
        if context.wyckoff_event == "spring":
            contributions["wyckoff_event"] = 2.0
            evidence.append("Wyckoff spring — false breakdown below support, real buyers stepping in")
        elif context.wyckoff_event == "upthrust":
            contributions["wyckoff_event"] = -2.0
            evidence.append("Wyckoff upthrust — false breakout above resistance, real sellers stepping in")
        elif context.wyckoff_event == "sign_of_strength":
            contributions["wyckoff_event"] = 1.5
            evidence.append("Wyckoff sign of strength — volume-confirmed breakout above resistance")
        elif context.wyckoff_event == "sign_of_weakness":
            contributions["wyckoff_event"] = -1.5
            evidence.append("Wyckoff sign of weakness — volume-confirmed breakdown below support")

        # Break of Structure
        if context.break_of_structure == "bullish":
            contributions["break_of_structure"] = 1.5
            evidence.append("Bullish break of structure (BOS)")
        elif context.break_of_structure == "bearish":
            contributions["break_of_structure"] = -1.5
            evidence.append("Bearish break of structure (BOS)")

        # Change of Character — trend güvenini azaltır
        if context.change_of_character:
            caveats.append("Change of character (CHoCH) detected — trend reversal risk")
            scale_all(0.6)

        # Fair Value Gap
        if context.fair_value_gap == "bullish":
            contributions["fair_value_gap"] = 0.5
            evidence.append("Bullish fair value gap (FVG) unfilled")
        elif context.fair_value_gap == "bearish":
            contributions["fair_value_gap"] = -0.5
            evidence.append("Bearish fair value gap (FVG) unfilled")

        # Swing structure
        if context.swing_structure == "higher_highs_higher_lows":
            contributions["swing_structure"] = 1.0
            evidence.append("Higher highs / higher lows — bullish swing structure")
        elif context.swing_structure == "lower_highs_lower_lows":
            contributions["swing_structure"] = -1.0
            evidence.append("Lower highs / lower lows — bearish swing structure")
        else:
            caveats.append("Mixed swing structure — no clear directional bias")

        # Likidite süpürme — genellikle ters yönlü bir hareketin habercisi
        if context.liquidity_sweep == "buy_side_swept":
            contributions["liquidity_sweep"] = -0.5
            evidence.append("Buy-side liquidity swept — potential reversal down")
        elif context.liquidity_sweep == "sell_side_swept":
            contributions["liquidity_sweep"] = 0.5
            evidence.append("Sell-side liquidity swept — potential reversal up")

        # Faz 223: klasik Fibonacci retracement — destek/dirençte olmak
        # tek başına yön belirlemez (fiyat bir seviyeden dönebilir de
        # kırıp geçebilir de), bu yüzden mevcut yapısal kanıtı (BOS/swing)
        # DOĞRULAYAN yönde hafifçe güçlendiriyor, kendi başına yeni bir
        # yön açmıyor.
        current_score = sum(contributions.values())
        if context.fibonacci_price_position == "at_support":
            if current_score > 0:
                contributions["fibonacci_confirm"] = 0.5
                evidence.append(f"Price at Fibonacci support ({context.fibonacci_nearest_level}) — confirms bullish structure")
            else:
                caveats.append(f"Price at Fibonacci support ({context.fibonacci_nearest_level}) but structure is bearish — mixed signal")
        elif context.fibonacci_price_position == "at_resistance":
            if current_score < 0:
                contributions["fibonacci_confirm"] = -0.5
                evidence.append(f"Price at Fibonacci resistance ({context.fibonacci_nearest_level}) — confirms bearish structure")
            else:
                caveats.append(f"Price at Fibonacci resistance ({context.fibonacci_nearest_level}) but structure is bullish — mixed signal")

        # Faz 268-sonrası — kullanıcı isteği: "fiyatın akümüle olduğu
        # bölgelere göre strateji" — gerçek Volume Profile (bkz.
        # signal_engine.compute_volume_profile). Fibonacci ile AYNI ilke:
        # yüksek-hacim bölgesi (gerçek biriktirme/support-resistance)
        # kendi başına yön açmıyor, mevcut yapısal kanıtı DOĞRULUYOR.
        current_score = sum(contributions.values())
        if context.near_high_volume_node:
            if current_score > 0:
                contributions["volume_profile_confirm"] = 0.5
                evidence.append("Price near a high-volume accumulation node — confirms bullish structure (real support)")
            elif current_score < 0:
                contributions["volume_profile_confirm"] = -0.5
                evidence.append("Price near a high-volume accumulation node — confirms bearish structure (real resistance)")
        if not context.in_value_area:
            caveats.append("Price outside the volume-profile value area (~70% of recent volume) — thinner liquidity here")

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
            feature_contributions={k: round(v, 4) for k, v in contributions.items()},
        ).recalculate()
