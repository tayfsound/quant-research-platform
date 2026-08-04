"""Replay Engine — thin facade over services/replay/ (the real deterministic
replay motor: decision_hash, snapshot_builder, ReplayVerifier). This class
keeps the public API that api/rest/replay.py and the dashboard already call;
the hashing/verification logic itself lives in services/replay/."""
from datetime import datetime
from typing import List, Dict, Optional

from database.repositories.belief_repository import BeliefRepository
from database.repositories.decision_persistor import DecisionPersistor
from services.cognitive_engine import CognitiveEngine
from contracts.context import CognitiveCycleContext
from contracts.decision_event import DecisionEvent
from services.replay.seed_manager import ReplaySeedManager
from services.replay.snapshot_builder import build_snapshot
from services.replay.replay_verifier import ReplayVerifier


class ReplayEngine:
    def __init__(
        self,
        belief_repo: Optional[BeliefRepository] = None,
        decision_repo: Optional[DecisionPersistor] = None,
    ):
        self.belief_repo = belief_repo
        self.decision_repo = decision_repo
        self._engine = None  # Lazy init

    @property
    def engine(self):
        """CognitiveEngine'i lazy olarak olustur."""
        if self._engine is None:
            self._engine = CognitiveEngine()
        return self._engine

    def list_available_sessions(self, limit: int = 100) -> List[Dict]:
        """Persist edilmis session'lari listele."""
        sessions = []
        if self.decision_repo:
            decisions = self.decision_repo.list_recent(limit=limit)
            seen = set()
            for d in decisions:
                sym = d.get("symbol", "unknown")
                if sym not in seen:
                    seen.add(sym)
                    sessions.append({
                        "session_id": f"session_{sym}",
                        "symbol": sym,
                        "decision_count": len([x for x in decisions if x.get("symbol") == sym]),
                    })
        return sessions

    def run_replay(
        self,
        session_id: str,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> Dict:
        """Belirli bir session'i geri oynat."""
        if not self.belief_repo or not self.decision_repo:
            return {"error": "repositories_not_configured", "session_id": session_id}

        beliefs = self.belief_repo.get_latest(limit=limit)
        if not beliefs:
            return {"error": "no_beliefs_found", "session_id": session_id}

        target_symbol = symbol or session_id.replace("session_", "")
        decisions = self.decision_repo.get_by_symbol(target_symbol, limit=limit)

        results = []
        for belief in beliefs:
            ctx = CognitiveCycleContext()
            ctx.market.symbol = belief.get("symbol", target_symbol)
            ctx.market.features = {"rsi": 50.0, "ema": 100.0, "macd": 0.0}
            ctx.decision.proposed_direction = belief.get("direction", "NEUTRAL")
            ctx.decision.confidence = belief.get("strength", 0.5)

            try:
                ctx = self.engine.run(ctx, persist=False)
                results.append({
                    "belief_id": str(belief.get("id")),
                    "direction": belief.get("direction"),
                    "engine_direction": ctx.decision.proposed_direction,
                    "match": belief.get("direction") == ctx.decision.proposed_direction,
                })
            except Exception as e:
                results.append({
                    "belief_id": str(belief.get("id")),
                    "error": str(e),
                })

        return {
            "session_id": session_id,
            "symbol": target_symbol,
            "belief_count": len(beliefs),
            "decision_count": len(decisions),
            "results": results,
            "match_rate": sum(1 for r in results if r.get("match")) / len(results) if results else 0.0,
        }

    def validate_replay_integrity(self, session_id: str) -> Dict:
        """Replay oncesi veri butunlugunu kontrol et."""
        if not self.belief_repo or not self.decision_repo:
            return {"valid": False, "reason": "repositories_not_configured"}

        beliefs = self.belief_repo.get_latest(limit=1)
        decisions = self.decision_repo.list_recent(limit=1)

        return {
            "valid": len(beliefs) > 0 and len(decisions) > 0,
            "belief_count": len(beliefs),
            "decision_count": len(decisions),
            "session_id": session_id,
        }

    def verify_integrity(self, decision_id: str) -> bool:
        """Verify a decision is reproducible: replay it and check the
        replayed outcome hashes identically to the original (services/replay/
        ReplayVerifier), rather than comparing against a stored hash column
        that doesn't exist in the schema."""
        result = self.replay_decision(decision_id, deterministic=True)
        return bool(result.get("verification", {}).get("verified", False))

    def replay_decision(self, decision_id: str, deterministic: bool = True) -> dict:
        """Replay a single decision by ID through CognitiveEngine, restoring
        state deterministically, and verify the replay against the original
        via services/replay/ (decision_hash + snapshot_builder + ReplayVerifier)."""
        if not self.decision_repo:
            return {'error': 'repositories_not_configured', 'decision_id': decision_id}

        decision = self.decision_repo.get_by_id(decision_id)
        if not decision:
            return {'error': 'decision_not_found', 'decision_id': decision_id}

        # Restore market snapshot if available
        # DB'de ayrı kolon yok; agent_contributions içinde saklanıyor
        snapshot_data = {}
        raw = {}
        agent_contributions = decision.get('agent_contributions', []) or []
        for contrib in agent_contributions:
            if isinstance(contrib, dict) and contrib.get('type') == 'market_snapshot':
                snapshot_data = contrib.get('data', {})
                raw = snapshot_data.get('raw_snapshot', {})
                break
        if not raw:
            # Fallback: doğrudan market_snapshot kolonu (gelecek şema)
            snapshot_data = decision.get('market_snapshot', {}) or {}
            raw = snapshot_data.get('raw_snapshot', {})

        original_event = DecisionEvent(
            symbol=decision.get('symbol', 'unknown'),
            final_action=decision.get('proposed_direction') or decision.get('direction'),
            final_size=decision.get('final_size', 0.0) or 0.0,
            confidence=decision.get('confidence', 0.0),
            market_snapshot=snapshot_data or None,
        )
        original_snapshot = build_snapshot(original_event)

        ctx = CognitiveCycleContext()
        ctx.market.symbol = original_event.symbol
        if raw:
            ctx.market.features = {
                k: v for k, v in raw.items()
                if k not in ('symbol', 'timestamp') and isinstance(v, (int, float, str))
            }
        ctx.decision.proposed_direction = (
            decision.get('proposed_direction') or decision.get('direction') or 'NEUTRAL'
        )
        ctx.decision.confidence = decision.get('confidence', 0.0)

        if deterministic:
            import hashlib
            seed_source = f"{decision_id}|{decision.get('symbol')}|{decision.get('confidence')}"
            seed_hash = hashlib.sha256(seed_source.encode()).hexdigest()
            ReplaySeedManager().set_seed(int(seed_hash[:8], 16))

        result_ctx = self.engine.run(ctx, persist=False)

        replayed_event = DecisionEvent(
            symbol=result_ctx.market.symbol,
            final_action=result_ctx.decision.proposed_direction,
            final_size=getattr(result_ctx.decision, 'final_size', 0.0) or 0.0,
            confidence=result_ctx.decision.confidence,
            market_snapshot=snapshot_data or None,
        )
        verification = ReplayVerifier().verify(original_snapshot, replayed_event)

        return {
            'decision_id': decision_id,
            'symbol': result_ctx.market.symbol,
            'direction': result_ctx.decision.proposed_direction,
            'confidence': result_ctx.decision.confidence,
            'risk_verdict': result_ctx.risk.evaluation.verdict if result_ctx.risk.evaluation else 'unknown',
            'snapshot_restored': bool(raw),
            'deterministic': deterministic,
            'verification': verification,
        }

