"""Replay Engine — persist edilmis belief+decision'i geri oynat."""
from datetime import datetime
from typing import List, Dict, Optional

from database.repositories.belief_repository import BeliefRepository
from database.repositories.decision_persistor import DecisionPersistor
from services.cognitive_engine import CognitiveEngine
from contracts.context import CognitiveCycleContext


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
        """Verify decision hash against stored signature."""
        import hashlib
        if not self.decision_repo:
            return False
        decision = self.decision_repo.get_by_id(decision_id)
        if not decision:
            return False
        raw = f"{decision.get('symbol')}|{decision.get('proposed_direction')}|{decision.get('confidence')}"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        stored = decision.get('integrity_hash', '')
        return expected == stored

    def replay_decision(self, decision_id: str, deterministic: bool = True) -> dict:
        """Replay a single decision by ID through CognitiveEngine — deterministic from snapshot."""
        if not self.decision_repo:
            return {'error': 'repositories_not_configured', 'decision_id': decision_id}

        decision = self.decision_repo.get_by_id(decision_id)
        if not decision:
            return {'error': 'decision_not_found', 'decision_id': decision_id}

        ctx = CognitiveCycleContext()
        ctx.market.symbol = decision.get('symbol', 'unknown')
        
        # Restore market snapshot if available
        # DB'de ayrı kolon yok; agent_contributions içinde saklanıyor
        snapshot = {}
        raw = {}
        agent_contributions = decision.get('agent_contributions', []) or []
        for contrib in agent_contributions:
            if isinstance(contrib, dict) and contrib.get('type') == 'market_snapshot':
                snapshot = contrib.get('data', {})
                raw = snapshot.get('raw_snapshot', {})
                break
        if not raw:
            # Fallback: doğrudan market_snapshot kolonu (gelecek şema)
            snapshot = decision.get('market_snapshot', {}) or {}
            raw = snapshot.get('raw_snapshot', {})
        if raw:
            ctx.market.features = {
                k: v for k, v in raw.items() 
                if k not in ('symbol', 'timestamp') and isinstance(v, (int, float, str))
            }
        
        ctx.decision.proposed_direction = decision.get('proposed_direction', 'NEUTRAL')
        ctx.decision.confidence = decision.get('confidence', 0.0)

        # Deterministik replay: seed + config hash
        if deterministic:
            import hashlib
            config_hash = hashlib.sha256(
                f"{decision_id}|{decision.get('symbol')}|{decision.get('confidence')}".encode()
            ).hexdigest()
            # Engine'e deterministik mod sinyali (seed-based)
            import random
            random.seed(config_hash[:16])

        result_ctx = self.engine.run(ctx, persist=False)

        return {
            'decision_id': decision_id,
            'symbol': result_ctx.market.symbol,
            'direction': result_ctx.decision.proposed_direction,
            'confidence': result_ctx.decision.confidence,
            'risk_verdict': result_ctx.risk.evaluation.verdict if result_ctx.risk.evaluation else 'unknown',
            'snapshot_restored': bool(raw),
            'deterministic': deterministic,
        }

