"""Learning Loop — outcome feedback + adaptive weight update."""

from enum import Enum

from contracts.agent import VOTING_AGENT_DOMAINS
from contracts.agent_performance import AgentPerformanceRecord
from contracts.decision_event import DecisionEvent
from contracts.outcome import DecisionEvaluation
from services.agent_memory import AgentMemory
from services.calibration import CalibrationMetrics
from services.weight_optimizer import WeightOptimizer
from services.weight_repository import WeightRepository


class LearningLoop:

    def __init__(self):
        self.calibration = CalibrationMetrics()
        self.agent_memory = AgentMemory()
        self.weight_repository = WeightRepository()
        self.weight_optimizer = WeightOptimizer(
            agent_memory=self.agent_memory,
            weight_repository=self.weight_repository,
        )

    def _apply_feedback(self, event, was_correct, pnl) -> None:
        self.calibration.record(
            event.confidence,
            was_correct,
        )
        # Faz 386 — kullanıcı bulgusu (macro ajanının rejime göre çok
        # farklı isabet gösterdiğinin doğrulanması sırasında bulundu):
        # "raw_snapshot" (ctx.market.raw_snapshot — OHLC/mikroyapı verisi)
        # hiçbir zaman "trend" alanı TAŞIMIYOR, bu her zaman "unknown"a
        # düşüyordu. trend/volatility_regime "features" alanında (ctx.
        # market.features) — position_closer.py::_extract_market_regime
        # zaten doğru yerden okuyor, burası atlanmış. Şu an bu metod
        # (LearningLoop.record) canlı akıştan hiç ÇAĞRILMIYOR (bkz.
        # cognitive_engine.py — sadece agent_memory referansı paylaşılıyor)
        # — bu yüzden bugüne dek gerçek etkisi yoktu, ama ileride tekrar
        # bağlanırsa doğru rejim etiketiyle kaydetsin diye düzeltildi.
        features = event.market_snapshot.get("features", {}) or {}
        trend = features.get("trend", "unknown")
        regime = trend if trend == "unknown" else f"{trend}_{features.get('volatility_regime', 'normal')}"
        # Faz 248: kritik bulgu — bu yol (services/orchestrator.py::
        # finalize_proposal, ForwardOutcome ile AYNI cycle'da geriye dönük
        # bir "n-bar" hesabı yapıyor, gerçekten zaman geçmesini beklemiyor)
        # PositionCloser'dan TAMAMEN BAĞIMSIZ, çok daha yüksek frekansta
        # (her trading cycle'da, her sembol için) AgentMemory'ye yazıyordu.
        # İki ayrı, düzeltilmiş bug'ı hâlâ taşıyordu: (1) Faz 211'in
        # düzelttiği "tek blanket was_correct her ajana uygulanıyor" hatası
        # (ajanın KENDİ yönü hiç kontrol edilmiyordu), (2) Faz 245'in
        # düzelttiği "WAIT diyen ajan bile ödüllendiriliyor/cezalandırılıyor"
        # hatası. Artık PositionCloser._record_agent_learning() ile BİREBİR
        # aynı mantık kullanılıyor, ve source="forward_estimate" ile açıkça
        # etiketleniyor — gerçek (source="live") kapanışlarla asla sessizce
        # karışmıyor.
        executed_direction = (event.final_action or "").upper()
        profitable = pnl > 0
        for opinion in event.agent_opinions:
            domain = opinion.get("domain")
            if isinstance(domain, Enum):
                domain = domain.value
            if isinstance(domain, dict):
                domain = domain.get("value")
            # Faz 229: kritik bulgu — burası önceden domain eksik/bozuksa
            # sessizce "unknown" ajanına düşüyordu, AgentMemory'ye sahte bir
            # domain sızdırıyordu (WeightOptimizer.propose_weights() sonra
            # bu sahte domain için de anlamsız bir ağırlık öneriyordu, insan
            # onay ekranını kirletiyordu). Artık gerçek 9 oy-veren ajandan
            # biri değilse kayıt tamamen atlanıyor.
            if str(domain) not in VOTING_AGENT_DOMAINS:
                continue
            agent_direction = (opinion.get("direction") or "").upper()
            if agent_direction not in ("LONG", "SHORT"):
                continue
            agent_was_correct = profitable if agent_direction == executed_direction else not profitable
            self.agent_memory.record(
                AgentPerformanceRecord(
                    agent_domain=str(domain),
                    direction=opinion.get("direction", ""),
                    confidence=opinion.get("confidence", 0.0),
                    raw_confidence=opinion.get("raw_confidence"),
                    was_correct=agent_was_correct,
                    pnl=pnl,
                    market_regime=regime,
                    symbol=event.symbol,
                    source="forward_estimate",
                )
            )

    def record(self, event: DecisionEvent, evaluation: DecisionEvaluation) -> None:
        outcome = evaluation.outcome
        was_correct = evaluation.was_prediction_correct
        self._apply_feedback(event, was_correct, outcome.pnl)

        from observability.metrics import learning_updates_total
        learning_updates_total.inc()

    def get_stats(self) -> dict:
        return {
            "brier_score": self.calibration.brier_score(),
            "ece": self.calibration.expected_calibration_error(),
            "total_predictions": len(self.calibration.predictions),
            "weight_domains": self.agent_memory.domains(),
        }
