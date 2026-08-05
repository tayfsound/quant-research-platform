"""Pattern Agent — Wyckoff/Elliott/market structure uzmanı."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.pattern import PatternContext


class PatternAgent:
    def __init__(self):
        self.agent_id = "pattern_agent_v1"

    def analyze(self, context: PatternContext) -> AgentOpinion:
        evidence = []
        caveats = []
        score = 0.0

        # Wyckoff fazı
        if context.structure_phase == "accumulation":
            score += 1.5
            evidence.append("Wyckoff accumulation phase detected")
        elif context.structure_phase == "distribution":
            score -= 1.5
            evidence.append("Wyckoff distribution phase detected")
        elif context.structure_phase == "markup":
            score += 1.0
            evidence.append("Markup phase — trend continuation likely")
        elif context.structure_phase == "markdown":
            score -= 1.0
            evidence.append("Markdown phase — trend continuation likely")

        # Break of Structure
        if context.break_of_structure == "bullish":
            score += 1.5
            evidence.append("Bullish break of structure (BOS)")
        elif context.break_of_structure == "bearish":
            score -= 1.5
            evidence.append("Bearish break of structure (BOS)")

        # Change of Character — trend güvenini azaltır
        if context.change_of_character:
            caveats.append("Change of character (CHoCH) detected — trend reversal risk")
            score *= 0.6

        # Fair Value Gap
        if context.fair_value_gap == "bullish":
            score += 0.5
            evidence.append("Bullish fair value gap (FVG) unfilled")
        elif context.fair_value_gap == "bearish":
            score -= 0.5
            evidence.append("Bearish fair value gap (FVG) unfilled")

        # Swing structure
        if context.swing_structure == "higher_highs_higher_lows":
            score += 1.0
            evidence.append("Higher highs / higher lows — bullish swing structure")
        elif context.swing_structure == "lower_highs_lower_lows":
            score -= 1.0
            evidence.append("Lower highs / lower lows — bearish swing structure")
        else:
            caveats.append("Mixed swing structure — no clear directional bias")

        # Likidite süpürme — genellikle ters yönlü bir hareketin habercisi
        if context.liquidity_sweep == "buy_side_swept":
            score -= 0.5
            evidence.append("Buy-side liquidity swept — potential reversal down")
        elif context.liquidity_sweep == "sell_side_swept":
            score += 0.5
            evidence.append("Sell-side liquidity swept — potential reversal up")

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
        ).recalculate()
