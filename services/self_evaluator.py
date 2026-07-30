"""Self Evaluator — ajanın kendi performansını analiz etmesi."""
from contracts.evaluation import BeliefAdjustment, Lesson, OutcomeAnalysis
from contracts.memory import EpisodicMemory, SemanticMemory


class SelfEvaluator:
    def __init__(self, episodic: EpisodicMemory, semantic: SemanticMemory):
        self.episodic = episodic
        self.semantic = semantic

    def analyze_outcomes(self, last_n: int = 20) -> OutcomeAnalysis:
        """Son N episode'u analiz et."""
        episodes = self.episodic.episodes[-last_n:]
        analysis = OutcomeAnalysis(total_evaluated=len(episodes))

        condition_stats: dict[str, dict] = {}

        for ep in episodes:
            is_win = ep.outcome and ep.outcome.get("pnl", 0) > 0
            if is_win:
                analysis.wins += 1
            else:
                analysis.losses += 1

            # Hangi koşullarda hata yapıldı?
            if ep.binding_expression:
                cond = ep.binding_expression
                if cond not in condition_stats:
                    condition_stats[cond] = {"total": 0, "wins": 0, "losses": 0}
                condition_stats[cond]["total"] += 1
                if is_win:
                    condition_stats[cond]["wins"] += 1
                else:
                    condition_stats[cond]["losses"] += 1

        analysis.win_rate = analysis.wins / max(analysis.total_evaluated, 1)
        analysis.condition_breakdown = condition_stats

        # En çok hata yapılan koşullar
        error_conditions = sorted(
            [(c, s) for c, s in condition_stats.items()],
            key=lambda x: x[1]["losses"] / max(x[1]["total"], 1),
            reverse=True,
        )
        analysis.top_error_conditions = [c for c, _ in error_conditions[:3]]

        return analysis

    def adjust_beliefs(self, analysis: OutcomeAnalysis) -> list[BeliefAdjustment]:
        """Analiz sonucuna göre belief'leri güncelle."""
        adjustments = []

        for belief in self.semantic.consolidated_beliefs:
            expr = belief.get("expression", "")
            if expr in analysis.condition_breakdown:
                stats = analysis.condition_breakdown[expr]
                condition_win_rate = stats["wins"] / max(stats["total"], 1)
                old_conf = belief.get("confidence", 0.5)
                new_conf = (old_conf + condition_win_rate) / 2

                if abs(new_conf - old_conf) > 0.05:
                    adj_type = "strengthen" if new_conf > old_conf else "weaken"
                    if new_conf < 0.3:
                        adj_type = "invalidate"

                    adjustments.append(BeliefAdjustment(
                        belief_expression=expr,
                        old_confidence=old_conf,
                        new_confidence=new_conf,
                        reason=f"Condition win rate: {condition_win_rate:.1%} over {stats['total']} episodes",
                        adjustment_type=adj_type,
                    ))
                    # Gerçek güncelleme
                    belief["confidence"] = new_conf
                    belief["evidence_count"] = belief.get("evidence_count", 0) + stats["total"]

        return adjustments

    def generate_lessons(self, analysis: OutcomeAnalysis, adjustments: list[BeliefAdjustment]) -> list[Lesson]:
        """Analiz ve güncellemelerden ders çıkar."""
        lessons = []

        if analysis.win_rate < 0.4:
            lessons.append(Lesson(
                lesson_text=f"Overall win rate critically low: {analysis.win_rate:.1%}",
                category="general",
                severity="critical",
            ))

        for cond in analysis.top_error_conditions:
            lessons.append(Lesson(
                lesson_text=f"High error rate under condition: {cond}",
                category="condition_specific",
                severity="warning",
            ))

        for adj in adjustments:
            if adj.adjustment_type == "invalidate":
                lessons.append(Lesson(
                    lesson_text=f"Belief invalidated: {adj.belief_expression} (confidence {adj.old_confidence:.2f} → {adj.new_confidence:.2f})",
                    category="model_error",
                    severity="critical",
                ))

        return lessons
