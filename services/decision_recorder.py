from pathlib import Path

"""Decision recorder — Phase 165 replay compatible."""

from contracts.decision_event import DecisionEvent
from database.connection import get_session
from database.repositories.decision_persistor import DecisionPersistor


class DecisionRecorder:
    def __init__(self, storage_path=None):
        self.storage_path = Path(storage_path) if storage_path else None
        if self.storage_path:
            self.storage_path.mkdir(parents=True, exist_ok=True)
        self.session = get_session()
        self.persistor = DecisionPersistor(self.session)

    def record(
        self,
        ctx,
        opinions=None,
        belief=None,
        debate_result=None,
        weight_snapshot_id=None,
        decision_fusion_entries=None,
        experiment_bucket=None,
    ) -> DecisionEvent:

        direction = (
            getattr(ctx.decision, "proposed_direction", None)
            or getattr(ctx.decision, "final_action", "WAIT")
        )

        # Faz 187: gerçek pozisyon yaşam döngüsü — sadece risk onaylı VE
        # yönlü (LONG/SHORT) bir işlem gerçekten "açılmış" sayılır. WAIT/
        # NEUTRAL veya risk tarafından reddedilen bir öneri hiçbir zaman
        # pozisyon açmaz (no_trade).
        risk_approved = ctx.risk.evaluation.verdict == "approved"
        is_directional = direction.upper() in ("LONG", "SHORT")
        opens_position = risk_approved and is_directional and getattr(ctx.decision, "final_size", 0.0) > 0

        agent_opinions_data = [op.model_dump() for op in (opinions or [])]
        if debate_result is not None:
            # Explainability chain (Sprint 16): debate_result used to be
            # accepted here and silently discarded — "hangi debate?" had no
            # answer for any real persisted decision. Folded into
            # agent_opinions (same list that flows into agent_contributions
            # in the DB) tagged distinctly so it's filterable.
            agent_opinions_data.append({
                "_type": "debate_result",
                "data": (
                    debate_result.model_dump()
                    if hasattr(debate_result, "model_dump")
                    else debate_result
                ),
            })

        # Faz 212: DecisionFusion'ın "neden reddetti/ayarladı" gerekçesi
        # (Negative EV / min_profit_target_pct) artık gerçekten kalıcı —
        # bkz. engines/cognitive_pipeline.py::RecordingStage.
        for entry in (decision_fusion_entries or []):
            agent_opinions_data.append({
                "type": "decision_fusion",
                "data": entry,
            })

        # filled_price varsa (orchestrator.py fill_engine.simulate ile
        # gerçek slippage uygulayıp set ediyor) onu kullan; yoksa (örn.
        # /cognitive/run fill simülasyonu yapmıyor) en azından gerçek
        # güncel kapanış fiyatına düş — hiçbir zaman uydurma bir sayı değil.
        entry_price = getattr(ctx.decision, "filled_price", None) or (ctx.market.raw_snapshot or {}).get("close")

        # Faz 192: RiskTargetStage'in gerçek ATR'den kurduğu risk/ödül
        # magnitüdlerini (ctx.decision.stop_loss/take_profit), pozisyon
        # gerçekten açıldığı andaki entry_price'a göre mutlak fiyat
        # seviyesine çeviriyoruz — PositionCloser bu seviyeleri kontrol edip
        # hedefine ulaşan/stop'a takılan pozisyonu vade dolmadan kapatabiliyor.
        stop_loss_price = None
        take_profit_price = None
        if opens_position and entry_price:
            risk_mag = getattr(ctx.decision, "stop_loss", None)
            reward_mag = getattr(ctx.decision, "take_profit", None)
            if risk_mag is not None and reward_mag is not None:
                if direction.upper() == "LONG":
                    stop_loss_price = entry_price - risk_mag
                    take_profit_price = entry_price + reward_mag
                else:
                    stop_loss_price = entry_price + risk_mag
                    take_profit_price = entry_price - reward_mag

        # Faz 255: kullanıcı isteği — token bazlı kaldıraç. Aynı capital_
        # per_trade "teminatı" leverage kadar daha büyük bir notional
        # kontrol ediyor (gerçek kaldıraçlı işlemin tanımı) — quantity
        # buna göre ölçekleniyor, gerçek likidasyon fiyatı hesaplanıyor.
        # Sembol için ayar yoksa leverage=1.0 (spot, önceki davranışla
        # birebir aynı, geriye dönük uyumlu).
        leverage = 1.0
        liquidation_price = None
        quantity = getattr(ctx.decision, "final_size", 0.0)
        if opens_position:
            leverage = self._symbol_leverage(ctx.market.symbol)
            if leverage > 1.0:
                quantity = quantity * leverage
                from simulator.margin import compute_liquidation_price
                liquidation_price = compute_liquidation_price(entry_price, direction, leverage)

        event = DecisionEvent(
            id=ctx.cycle_id,
            timestamp=ctx.timestamp,
            symbol=ctx.market.symbol,
            proposed_direction=direction,
            final_action=direction,
            final_size=getattr(ctx.decision, "final_size", 0.0),
            confidence=getattr(ctx.decision, "confidence", 0.0),
            agent_opinions=agent_opinions_data,
            risk_evaluation=ctx.risk.evaluation.model_dump(),
            market_snapshot={
                "symbol": ctx.market.symbol,
                "timeframe": ctx.market.timeframe,
                "features": ctx.market.features,
                "raw_snapshot": ctx.market.raw_snapshot,
            },
            belief_state=(
                belief.model_dump()
                if belief and hasattr(belief, "model_dump")
                else None
            ),
            outcome=None,
            weight_snapshot_id=weight_snapshot_id,
            # Explainability chain: without this, belief_snapshot_id was
            # always NULL in the decisions table — belief IS saved
            # separately (MemoryService.store_belief in RecordingStage) but
            # nothing linked the decision row back to it. "hangi belief?"
            # was unanswerable for any real decision.
            belief_snapshot_id=belief.id if belief is not None else None,
            status="open" if opens_position else "no_trade",
            entry_price=entry_price if opens_position else None,
            quantity=quantity if opens_position else None,
            opened_at=ctx.timestamp if opens_position else None,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            leverage=leverage,
            liquidation_price=liquidation_price,
            timeframe=ctx.market.timeframe,
            experiment_bucket=experiment_bucket,
        )

        self.persistor.persist(event)

        if self.storage_path:
            log_file = self.storage_path / f"decision_{event.id}.json"
            log_file.write_text(event.model_dump_json(indent=2))

        return event

    def _symbol_leverage(self, symbol: str) -> float:
        """Faz 255: kullanıcı isteği — token bazlı kaldıraç
        (Settings'ten, {"BTCUSDT": 10, "XAUTUSDT": 25} gibi bir JSON).
        Ayarlanmamış/bozuk/eksik bir sembol için her zaman 1.0 (spot,
        kaldıraçsız) döner — fail-closed, asla icat edilmiş bir kaldıraç
        uygulanmaz."""
        import json

        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory

        try:
            with SessionFactory.get_session() as session:
                raw = AppSettingsRepository(session).get("symbol_leverage")
            mapping = json.loads(raw) if raw else {}
            leverage = float(mapping.get(symbol, 1.0))
            return leverage if leverage >= 1.0 else 1.0
        except Exception:
            return 1.0

    def replay(self, decision_id: str):
        data = self.persistor.get_by_id(decision_id)

        if data is None:
            return None

        return DecisionEvent(
            id=data["id"],
            timestamp=data["timestamp"],
            symbol=data["symbol"],
            proposed_direction=data.get("direction"),
            final_action=data.get("direction"),
            final_size=data.get("size", 0.0),
            confidence=data.get("confidence", 0.0),
            weight_snapshot_id=data.get("weight_snapshot_id"),
            belief_snapshot_id=data.get("belief_snapshot_id"),
        )

    def list_decisions(self, limit: int = 100):
        return self.persistor.list_recent(limit)
