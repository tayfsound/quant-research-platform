from pathlib import Path

"""Decision recorder — Phase 165 replay compatible."""

from contracts.decision_event import DecisionEvent
from database.connection import get_session
from database.repositories.decision_persistor import DecisionPersistor


class DecisionRecorder:
    def __init__(self, storage_path=None, execution_service=None):
        self.storage_path = Path(storage_path) if storage_path else None
        if self.storage_path:
            self.storage_path.mkdir(parents=True, exist_ok=True)
        self.session = get_session()
        self.persistor = DecisionPersistor(self.session)
        # Faz 315 — Execution Layer, Faz 1. execution_service enjekte
        # edilebilir (testler için) — verilmezse gerçek ExecutionService
        # kurulur, ama anahtar yoksa (varsayılan durum) is_configured()
        # False kalır ve bu SIFIR maliyetli, ağa hiç dokunmaz.
        if execution_service is None:
            from services.execution_service import ExecutionService

            execution_service = ExecutionService()
        self.execution_service = execution_service

    def record(
        self,
        ctx,
        opinions=None,
        belief=None,
        debate_result=None,
        weight_snapshot_id=None,
        decision_fusion_entries=None,
        experiment_bucket=None,
        portfolio_confidence_discounts=None,
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

        # Kullanıcı bulgusu: explain sayfası tek bir confidence sayısı
        # gösteriyordu, portföy korelasyon/ENB indiriminin confidence'ı
        # MetaStage'in ACT/REDUCE kararından SONRA düşürdüğü hiç
        # görünmüyordu — decision_fusion ile AYNI desen.
        for entry in (portfolio_confidence_discounts or []):
            agent_opinions_data.append({
                "type": "portfolio_confidence_discount",
                "data": entry,
            })

        # filled_price varsa (orchestrator.py fill_engine.simulate ile
        # gerçek slippage uygulayıp set ediyor) onu kullan; yoksa (örn.
        # /cognitive/run fill simülasyonu yapmıyor) en azından gerçek
        # güncel kapanış fiyatına düş — hiçbir zaman uydurma bir sayı değil.
        entry_price = getattr(ctx.decision, "filled_price", None) or (ctx.market.raw_snapshot or {}).get("close")

        # Faz 362 — kullanıcı bulgusu: "council'in ara sıra bir cycle'da
        # tersine dönmesi çoğunlukla gerçek bir trend değişimi değil,
        # gürültü — bu gürültüye güvenerek yeni pozisyonlara da girebilir."
        # Gerçek 3619 kapanmış pozisyonla (10-24 Ağustos, mekanik
        # stratejiler hariç) doğrulandı: girişten hemen önce o sembol/
        # yönde 0-3 ardışık tutarlı cycle varken işlemler TEK TEK ortalama
        # ZARAR ediyordu (run=0: -$4.96, run=3: -$11.89) — run=4'te İLK kez
        # net pozitif (+$5.03) oluyor. TOPLAM kârı (hacim×kalite dengesini
        # doğru yakalayan tek metrik) maksimize eden eşik de bağımsız
        # olarak AYNI noktaya (N=4, $116,335 — N=5-7 istatistiksel
        # ayırt edilemez şekilde platoluyor, sonrası düşüyor) işaret etti
        # (bkz. analytics/signal_persistence.py, services/signal_
        # persistence_gatherer.py — optimum N veri büyüdükçe değişebilir
        # diye Genel Özet panelinde SÜREKLİ yeniden ölçülüyor, ama canlı
        # eşik burada AYRI bir ayarla — kullanıcı bilinçli karar vermeden
        # otomatik kaymasın diye).
        if opens_position and experiment_bucket is None:
            from analytics.signal_persistence import (
                consistent_direction_run_length,
                is_fresh_signal_blocked,
            )
            from database.repositories.app_settings_repository import AppSettingsRepository

            settings_repo = AppSettingsRepository(self.session)
            if settings_repo.get("signal_persistence_gate_enabled") == "true":
                min_required = int(settings_repo.get("signal_persistence_min_consistent_cycles"))
                prior = self.persistor.list_recent_directions_for_symbol(ctx.market.symbol, limit=min_required)
                run_length = consistent_direction_run_length(prior, direction)
                if is_fresh_signal_blocked(run_length, min_required):
                    opens_position = False

        # Faz 350 — Pozisyon Havuzu / Max Confidence Modu: normal council
        # yolunda (deneysel bucket'sız) risk-onaylı bir açılış, ayar
        # açıksa hemen açılmak yerine bir pencere boyunca havuzlanabilir
        # (bkz. services/position_pool.py) — sonra sadece en yüksek
        # confidence'lı top-K TAZE fiyattan açılır. pump_fade/basis_arb/
        # pairs_trading zaten kendi experiment_bucket'ıyla council
        # pipeline'ını (dolayısıyla bu fonksiyonu) hiç çağırmıyor, bu
        # koldan etkilenmiyorlar. Ayar kapalıyken (varsayılan) try_pool_
        # candidate() hiçbir şey yapmadan False döner — davranış birebir
        # aynı kalır.
        if opens_position and experiment_bucket is None:
            from services.position_pool import try_pool_candidate

            if try_pool_candidate(
                ctx, direction, entry_price,
                weight_snapshot_id=weight_snapshot_id,
                belief_snapshot_id=belief.id if belief is not None else None,
            ):
                opens_position = False

        # Faz 361 — kullanıcı bulgusu: aynı sembol/yönde açık pozisyon
        # varken daha kötü fiyattan üste eklemek (piramitleme + tepeden
        # giriş) SADECE "bullish_low" rejiminde gerçekten avantajlı
        # (bkz. analytics/pyramid_regime_gate.py — gerçek 3826 kararlık
        # AI-only veriyle ölçüldü). Kullanıcı kararı: diğer TÜM
        # rejimlerde (unknown dahil, fail-closed) kesin olarak yasakla.
        # Position Pool (Faz 350) yoluyla açılan adaylar burada DEĞİL,
        # services/position_pool.py::resolve_due_pool_windows()'ta
        # (TAZE fiyattan, council market context'i olmadan) açılıyor —
        # bu kapı ORAYA henüz bağlanmadı (havuz varsayılan kapalı,
        # düşük öncelik).
        if opens_position and entry_price and experiment_bucket is None:
            from analytics.pyramid_regime_gate import is_worse_price_pyramid_blocked
            from database.repositories.app_settings_repository import AppSettingsRepository

            settings_repo = AppSettingsRepository(self.session)
            if settings_repo.get("pyramid_regime_gate_enabled") == "true":
                allowed_regime = settings_repo.get("pyramid_worse_price_allowed_regime")
                existing_avg = self.persistor.avg_open_entry_price_by_symbol_direction(
                    ctx.market.symbol
                ).get(direction)
                features = ctx.market.features or {}
                trend = features.get("trend", "unknown")
                market_regime = (
                    f"{trend}_{features.get('volatility_regime', 'normal')}" if trend != "unknown" else None
                )
                if is_worse_price_pyramid_blocked(
                    direction, entry_price, existing_avg, market_regime, allowed_regime=allowed_regime
                ):
                    opens_position = False

        # Faz 192: RiskTargetStage'in gerçek ATR'den kurduğu risk/ödül
        # magnitüdlerini (ctx.decision.stop_loss_distance/take_profit_
        # distance), pozisyon gerçekten açıldığı andaki entry_price'a göre
        # mutlak fiyat seviyesine çeviriyoruz — PositionCloser bu seviyeleri
        # kontrol edip hedefine ulaşan/stop'a takılan pozisyonu vade
        # dolmadan kapatabiliyor.
        stop_loss_price = None
        take_profit_price = None
        if opens_position and entry_price:
            risk_mag = getattr(ctx.decision, "stop_loss_distance", None)
            reward_mag = getattr(ctx.decision, "take_profit_distance", None)
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
        #
        # Faz 268-sonrası — kritik, gerçek olay (DOLOUSDT): symbol_leverage
        # ayarı, o sembolün GERÇEK ATR-tabanlı stop mesafesine hiç
        # bakmadan uygulanıyordu. simulator/margin.py::max_safe_leverage
        # (Faz 260) tam bu senaryo için yazılmıştı ama burada hiç
        # çağrılmıyordu — geniş bir stop mesafesi (ör. DOLOUSDT'de ~%20)
        # yüksek kaldıraçla (5x) birleşince likidasyon fiyatı stop'tan
        # ÖNCE geliyordu, pozisyon planlanan zararı hiç görmeden tüm
        # teminatı kaybediyordu. Artık her pozisyon açılışında kaldıraç,
        # O SEMBOLÜN gerçek stop mesafesine göre güvenli üst sınıra
        # otomatik kırpılıyor — configured leverage sadece bir TAVAN,
        # asla dayatılan bir taban değil (AI kendi riskini asla
        # gevşetmez, sadece sıkılaştırır ilkesiyle tutarlı).
        leverage = 1.0
        liquidation_price = None
        quantity = getattr(ctx.decision, "final_size", 0.0)
        if opens_position:
            leverage_override = getattr(ctx.decision, "leverage_override", None)
            if leverage_override is not None:
                # Faz 363 — bkz. contracts/contexts/decision.py::
                # leverage_override gerekçesi. Sembol/piramit/güvenlik-
                # tavanı hesaplarının HİÇBİRİ uygulanmaz — çağıran bu
                # değeri KESİN olarak istiyor (ör. basis-arb'ın spot
                # bacağı için leverage=1.0).
                leverage = leverage_override
            else:
                leverage = self._symbol_leverage(ctx.market.symbol)
                if leverage > 1.0 and stop_loss_price and entry_price:
                    from simulator.margin import max_safe_leverage
                    stop_distance_pct = abs(entry_price - stop_loss_price) / entry_price
                    safe_leverage = max_safe_leverage(stop_distance_pct)
                    if safe_leverage is not None:
                        leverage = max(1.0, min(leverage, safe_leverage))

                # Faz 361-devam — kullanıcı bulgusu: aynı sembol/yönde art
                # arda 5x kaldıraçlı pozisyonlar (piramitleme) yön yanlış
                # çıkınca leverage × yığın derinliği kadar büyüyen bir kayıp
                # üretiyor (gerçek ZECUSDT örneği: ~$6.675 kayıp, 5x + 4-5
                # kat yığılma). analytics/pyramid_regime_gate.py'nin
                # (fiyat/rejim boyutu) TAMAMLAYICISI — bu, kaç tane zaten
                # açık olduğuna göre kaldıracı orantılı düşürüyor.
                # ctx.risk.same_direction_open_counts zaten RiskGateStage
                # için bu cycle'da hesaplanmış (services/risk_state.py) —
                # tekrar sorgu atmıyoruz.
                if leverage > 1.0:
                    from simulator.margin import pyramid_dampened_leverage
                    existing_same_direction_count = ctx.risk.same_direction_open_counts.get(direction, 0)
                    leverage = pyramid_dampened_leverage(leverage, existing_same_direction_count)

            if leverage > 1.0:
                quantity = quantity * leverage
                from simulator.margin import compute_liquidation_price
                liquidation_price = compute_liquidation_price(entry_price, direction, leverage)

        # Faz 315 — Execution Layer, Faz 1. Kullanıcı isteği: "sistem
        # baştan sona saf simülasyon, gerçek bir emir asla borsaya
        # gitmiyor — BOME/MUBARAK'ta kayıp bu yüzden kontrol döngüsünün
        # geç fark etmesinden kaynaklandı." execution_mode="testnet"
        # ise (sembol bazında ya da global) gerçek Binance Futures
        # Testnet emri gönderilir; entry_price/quantity GERÇEK dolum
        # değerleriyle DEĞİŞTİRİLİR (asla tahmini fill_engine değeri
        # değil). Emir teyit edilemezse (ExecutionService fail-closed
        # None döner) opens_position SAHTEN False'a çekilir — hiçbir
        # zaman uydurma bir "open" satırı yazılmaz, dürüstçe "no_trade"
        # olarak kaydedilir.
        execution_mode = None
        exchange_order_id = None
        exchange_client_order_id = None
        exchange_stop_order_id = None
        exchange_tp_order_id = None
        if opens_position:
            resolved_execution_mode = self._resolve_execution_mode(ctx.market.symbol)
            if resolved_execution_mode == "testnet" and self.execution_service.is_configured():
                exec_result = self.execution_service.open_position(
                    decision_id=ctx.cycle_id,
                    symbol=ctx.market.symbol,
                    direction=direction,
                    quantity=quantity,
                    stop_loss_price=stop_loss_price,
                    take_profit_price=take_profit_price,
                )
                if exec_result is None:
                    opens_position = False
                else:
                    execution_mode = "testnet"
                    entry_price = exec_result.entry_price
                    quantity = exec_result.executed_qty
                    exchange_order_id = exec_result.exchange_order_id
                    exchange_client_order_id = exec_result.exchange_client_order_id
                    exchange_stop_order_id = exec_result.exchange_stop_order_id
                    exchange_tp_order_id = exec_result.exchange_tp_order_id
            else:
                # resolved_execution_mode "testnet" olsa bile gerçek
                # anahtar yoksa (is_configured() False) fail-closed
                # olarak "simulated" gibi davranmaya devam ediyoruz —
                # asla yarım bir emir denemesi yapılmıyor.
                execution_mode = "simulated"

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
            decision_latency_ms=self._compute_decision_latency_ms(ctx),
            execution_mode=execution_mode,
            exchange_order_id=exchange_order_id,
            exchange_client_order_id=exchange_client_order_id,
            exchange_stop_order_id=exchange_stop_order_id,
            exchange_tp_order_id=exchange_tp_order_id,
        )

        self.persistor.persist(event)

        if self.storage_path:
            log_file = self.storage_path / f"decision_{event.id}.json"
            log_file.write_text(event.model_dump_json(indent=2))

        return event

    def _resolve_execution_mode(self, symbol: str) -> str:
        """Faz 315 — _symbol_leverage ile AYNI desen: execution_mode_
        symbols haritasında sembol için açık bir mod varsa o kullanılır,
        yoksa global execution_mode ayarı (varsayılan "simulated").
        Herhangi bir hata/eksik ayar fail-closed "simulated" — asla
        istemeden testnet moduna düşülmez."""
        import json

        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory

        try:
            with SessionFactory.get_session() as session:
                repo = AppSettingsRepository(session)
                raw_map = repo.get("execution_mode_symbols")
                global_mode = repo.get("execution_mode") or "simulated"
            mapping = json.loads(raw_map) if raw_map else {}
            return mapping.get(symbol, global_mode)
        except Exception:
            return "simulated"

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

    def _compute_decision_latency_ms(self, ctx) -> float:
        """Faz 268-sonrası — kritik bulgu: DecisionEvent.decision_latency_ms
        hiç doldurulmuyordu (her zaman varsayılan 0.0) — ml/training/
        feature_extractor.py bunu gerçek bir özellik gibi okuyordu ama
        aslında hep sabit sıfırdı. Kararın dayandığı son bar'ın ne kadar
        eski olduğunu (orchestrator.py::build_cognitive_context'in
        raw_snapshot'a yazdığı GERÇEK last_bar_timestamp) ctx.timestamp'e
        (kararın verildiği an) göre ölçer. Veri yoksa/bozuksa (fail-closed)
        0.0 — asla uydurulmuş bir gecikme değeri üretilmez."""
        last_bar_ts_raw = (ctx.market.raw_snapshot or {}).get("last_bar_timestamp")
        if not last_bar_ts_raw:
            return 0.0
        try:
            from datetime import datetime

            last_bar_ts = datetime.fromisoformat(last_bar_ts_raw)
            decided_at = ctx.timestamp
            if last_bar_ts.tzinfo is None or decided_at.tzinfo is None:
                return 0.0
            latency_seconds = (decided_at - last_bar_ts).total_seconds()
            return max(0.0, latency_seconds * 1000.0)
        except (ValueError, TypeError):
            return 0.0

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
