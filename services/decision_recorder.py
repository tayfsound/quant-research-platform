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
        cross_asset_context_entries=None,
        historical_analog_override_entries=None,
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

        # FIL Faz C — kullanıcı isteği: cross-asset causal bağlam (Faz
        # 331, Granger causality) kalıcı hâle geldi — decision_fusion/
        # portfolio_confidence_discount ile AYNI desen.
        for entry in (cross_asset_context_entries or []):
            agent_opinions_data.append({
                "type": "cross_asset_context",
                "data": entry,
            })

        # Faz 394 — kullanıcı isteği: HistoricalAnalogOverrideStage'in
        # belief.strength'i override ettiği anlar da AYNI desende kalıcı.
        for entry in (historical_analog_override_entries or []):
            agent_opinions_data.append({
                "type": "historical_analog_override",
                "data": entry,
            })

        # Faz 375 — 0.5266/multi-timeframe cascade instrumentation
        # (kullanıcı isteği): services/orchestrator.py::propose_multi_
        # timeframe()'in "timeframe_belief" kaydı (15m/4h/medium-term
        # kırılımı + Bayesian birleştirilmiş sonuç) HESAPLANIYORDU ve
        # Metacognition.evaluate_confidence()'ı GERÇEKTEN etkiliyordu ama
        # hiçbir zaman persist edilmiyordu — "confidence neden bu sayıya
        # yakınsadı?" sorusunun cevabı DB'de yoktu. debate_result/
        # decision_fusion ile AYNI desen: hem tam ham veri (per_timeframe
        # dahil) agent_contributions'a, hem özet iki alan (mtf_direction/
        # mtf_confidence) ayrı sütunlara.
        mtf_direction = None
        mtf_confidence = None
        if hasattr(ctx, "cognition"):
            for item in ctx.cognition.relevant_knowledge:
                if item.get("type") == "timeframe_belief":
                    agent_opinions_data.append(item)
                    data = item.get("data", {})
                    mtf_direction = data.get("combined_direction")
                    mtf_confidence = data.get("combined_confidence")
                    break

        # filled_price varsa (orchestrator.py fill_engine.simulate ile
        # gerçek slippage uygulayıp set ediyor) onu kullan; yoksa (örn.
        # /cognitive/run fill simülasyonu yapmıyor) en azından gerçek
        # güncel kapanış fiyatına düş — hiçbir zaman uydurma bir sayı değil.
        entry_price = getattr(ctx.decision, "filled_price", None) or (ctx.market.raw_snapshot or {}).get("close")

        # Faz 362 — signal_persistence_gate BURADAYDI (girişten önce N
        # ardışık tutarlı cycle şartı). Faz 395 (2026-09-01) — kullanıcı
        # isteği: "Kaldıralım evet. Döngü süresi çok üzüyor sistem aksiyon
        # alamıyor problem." Bir döngü ~15-30dk sürdüğü için 4 ardışık
        # tutarlı döngü şartı, bir sembolün açılabilmesi için saatlerce
        # fikrini değiştirmemesini gerektiriyordu — döngü süresiyle
        # BİRLEŞİNCE aşırı kısıtlayıcı hale geliyordu. Tamamen kaldırıldı.
        # `analytics/signal_persistence.py::consistent_direction_run_
        # length` ve ölçüm panelinin (services/signal_persistence_
        # gatherer.py, Genel Özet'teki "Sinyal Tutarlılığı Eşiği" kartı)
        # KENDİSİ DOKUNULMADI — hâlâ "veriye göre optimum ne olurdu"
        # sorusuna cevap veriyor, sadece artık canlı bir gate'e bağlı
        # değil. `is_fresh_signal_blocked` (SADECE bu gate'in tüketicisiydi)
        # analytics/signal_persistence.py'den de kaldırıldı.

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
                    agent_opinions_data.append({
                        "type": "gate_block",
                        "data": {
                            "gate": "pyramid_regime_gate",
                            "reason": "worse_price_pyramid_outside_allowed_regime",
                            "market_regime": market_regime,
                            "existing_avg_entry_price": existing_avg,
                        },
                    })

        # Kullanıcı isteği (2026-08-27): "sistemin işlem aldığı rejimleri
        # de aç kapa yapabilirsek süper olur." AI konseyi-özel (pyramid_
        # regime_gate/strategy_gate ile AYNI experiment_bucket kısıtı) —
        # pump_fade kendi rejim kavramını kullanmıyor, bu kapı onu
        # etkilemiyor.
        if opens_position and entry_price and experiment_bucket is None:
            import json as _json

            from analytics.regime_trading_gate import is_regime_trading_blocked
            from database.repositories.app_settings_repository import AppSettingsRepository

            raw_map = AppSettingsRepository(self.session).get("regime_trading_enabled")
            try:
                regime_enabled_map = _json.loads(raw_map) if raw_map else {}
            except (ValueError, TypeError):
                regime_enabled_map = {}
            features = ctx.market.features or {}
            trend = features.get("trend", "unknown")
            market_regime = (
                f"{trend}_{features.get('volatility_regime', 'normal')}" if trend != "unknown" else None
            )
            if is_regime_trading_blocked(market_regime, regime_enabled_map):
                opens_position = False
                agent_opinions_data.append({
                    "type": "gate_block",
                    "data": {
                        "gate": "regime_trading_gate",
                        "reason": "regime_disabled_by_user",
                        "market_regime": market_regime,
                    },
                })

        # Kullanıcı isteği (2026-08-28): Dashboard'daki "LONG/SHORT kazanma
        # oranı" kartlarına manuel bir aç/kapa anahtarı — Grok raporunun
        # SHORT'u otomatik daralt/kapat önerisine karşı, kullanıcı açıkça:
        # "short işlemlerini kısıtlamayalım, ben gerekli görürsem
        # dashboard'dan kapatırım" dedi. Bu yüzden varsayılan HER ZAMAN
        # açık (fail-open) — sadece kullanıcı elle kapatırsa etkili olur,
        # rapor/model asla otomatik tetiklemez.
        if opens_position and experiment_bucket is None:
            import json as _json

            from analytics.direction_trading_gate import is_direction_trading_blocked
            from database.repositories.app_settings_repository import AppSettingsRepository

            raw_map = AppSettingsRepository(self.session).get("direction_trading_enabled")
            try:
                direction_enabled_map = _json.loads(raw_map) if raw_map else {}
            except (ValueError, TypeError):
                direction_enabled_map = {}
            if is_direction_trading_blocked(direction, direction_enabled_map):
                opens_position = False
                agent_opinions_data.append({
                    "type": "gate_block",
                    "data": {
                        "gate": "direction_trading_gate",
                        "reason": "direction_disabled_by_user",
                        "direction": direction,
                    },
                })

        # Kullanıcı isteği (2026-08-28): canlıya kademeli geçiş için,
        # yukarıdaki rejim kapısından DAHA GRANÜLER bir kontrol — MAE/MFE
        # Güven Aralığı sayfasının (direction|regime|volatility_regime)
        # kovaları. Yukarıdaki market_regime'den (hızlı EMA20/50 trend)
        # FARKLI bir sınıflandırıcı: long_term_trend_regime (yavaş
        # 200-EMA, bkz. market_data/features/signal_engine.py::_long_
        # term_trend_regime) — MAE/MFE'nin kendi ürettiği etiketle
        # birebir eşleşsin diye icat edilmiyor, orchestrator.py'nin zaten
        # doldurduğu ctx.market.features'tan okunuyor.
        if opens_position and experiment_bucket is None:
            import json as _json

            from analytics.mae_mfe_bucket_trading_gate import (
                build_bucket_key,
                is_mae_mfe_bucket_trading_blocked,
            )
            from database.repositories.app_settings_repository import AppSettingsRepository
            from services.agent_memory import asset_class_trading_category

            raw_map = AppSettingsRepository(self.session).get("mae_mfe_bucket_trading_enabled")
            try:
                bucket_enabled_map = _json.loads(raw_map) if raw_map else {}
            except (ValueError, TypeError):
                bucket_enabled_map = {}
            features = ctx.market.features or {}
            bucket_key = build_bucket_key(
                direction,
                features.get("long_term_trend_regime", "unknown"),
                features.get("volatility_regime", "unknown"),
                asset_class_trading_category(ctx.market.symbol) or "unknown",
            )
            if is_mae_mfe_bucket_trading_blocked(bucket_key, bucket_enabled_map):
                opens_position = False
                agent_opinions_data.append({
                    "type": "gate_block",
                    "data": {
                        "gate": "mae_mfe_bucket_trading_gate",
                        "reason": "bucket_disabled_by_user",
                        "bucket_key": bucket_key,
                    },
                })

        # Kullanıcı isteği (2026-08-28): "kararı vermeden önce burayı
        # tarayacak, ajan gruplarının başarısını ölçecek — %80'in altında
        # kalıyorsa pozisyonu açmayacak." Rapor HAFTALIK (bkz. analytics/
        # agent_combination_reliability_gate.py — her kararda 2000 işlemi
        # yeniden taramak çok pahalı olurdu, diğer periyodik-sınıflandırmalı
        # kapılarla AYNI ilke). Mekanik stratejiler council oylaması
        # kullanmıyor, diğer AI-konseyi-özel kapılarla AYNI kısıt.
        if opens_position and experiment_bucket is None:
            from analytics.agent_combination_reliability import agreeing_domains_for_decision
            from analytics.agent_combination_reliability_gate import (
                DEFAULT_MIN_WIN_RATE,
                is_agent_combination_trading_blocked,
                trustworthy_known_pairs,
            )
            from database.repositories.agent_combination_reliability_report_repository import (
                AgentCombinationReliabilityReportRepository,
            )
            from database.repositories.app_settings_repository import AppSettingsRepository

            settings_repo = AppSettingsRepository(self.session)
            if settings_repo.get("agent_combination_gate_enabled") == "true":
                min_win_rate_raw = settings_repo.get("agent_combination_gate_min_win_rate")
                min_win_rate = float(min_win_rate_raw) if min_win_rate_raw else DEFAULT_MIN_WIN_RATE
                report = AgentCombinationReliabilityReportRepository(self.session).get_latest()
                if report and report.get("result"):
                    known_pairs = trustworthy_known_pairs(report["result"].get("pairs") or [])
                    agreeing_domains = agreeing_domains_for_decision(agent_opinions_data, direction)
                    if is_agent_combination_trading_blocked(agreeing_domains, known_pairs, min_win_rate):
                        opens_position = False
                        agent_opinions_data.append({
                            "type": "gate_block",
                            "data": {
                                "gate": "agent_combination_gate",
                                "reason": "known_low_reliability_agent_combination",
                                "agreeing_domains": sorted(agreeing_domains) if agreeing_domains else [],
                                "min_win_rate": min_win_rate,
                            },
                        })

        # Backlog #17 — kullanıcı isteği: "tepeden/dipten kovalıyorsa"
        # (kritik bir seviyeden çok uzaktaysa) giriş engellensin. Gerçek
        # veriyle (450+ karar) kalibre edildi (bkz. analytics/pivot_
        # distance_gate.py) — SADECE large-cap'te gerçek/monotonik bir
        # ilişki bulundu (small-cap'te desen TERS çıktı, orada hiç
        # uygulanmıyor). ctx.market.features["nearest_pivot_distance_pct"]
        # orchestrator.py'de zaten fetch edilmiş daily_data'dan (ekstra
        # ağ isteği yok) hesaplanıyor.
        if opens_position and entry_price and experiment_bucket is None:
            from analytics.pivot_distance_gate import DEFAULT_THRESHOLD_PCT, is_pivot_distance_entry_blocked
            from database.repositories.app_settings_repository import AppSettingsRepository
            from services.agent_memory import crypto_cap_tier

            settings_repo = AppSettingsRepository(self.session)
            if settings_repo.get("pivot_distance_gate_enabled") == "true":
                threshold_raw = settings_repo.get("pivot_distance_gate_threshold_pct")
                threshold_pct = float(threshold_raw) if threshold_raw else DEFAULT_THRESHOLD_PCT
                is_large_cap = crypto_cap_tier(ctx.market.symbol) == "large_cap"
                distance_pct = (ctx.market.features or {}).get("nearest_pivot_distance_pct")
                if is_pivot_distance_entry_blocked(is_large_cap, distance_pct, threshold_pct=threshold_pct):
                    opens_position = False
                    agent_opinions_data.append({
                        "type": "gate_block",
                        "data": {
                            "gate": "pivot_distance_gate",
                            "reason": "too_far_from_pivot",
                            "distance_pct": distance_pct,
                            "threshold_pct": threshold_pct,
                        },
                    })

        # Kullanıcı isteği (2026-08-27): "Emtia, Kripto, Hisse Senedi'ni
        # aç kapa yapabileceğimiz modüller." AI konseyi/pump_fade AYRIMI
        # YOK (experiment_bucket kontrolü yok) — "kripto'yu kapat" pump_
        # fade'i de kapsamalı, o zaten sadece kripto işlem görüyor. Kontrol
        # UI'ı Dashboard'daki asset-class kartında (Settings'te DEĞİL —
        # bkz. proje hafızası "settings placement: contextual").
        if opens_position:
            import json as _json

            from analytics.asset_class_trading_gate import is_asset_class_trading_blocked
            from database.repositories.app_settings_repository import AppSettingsRepository
            from services.agent_memory import asset_class_trading_category

            raw_map = AppSettingsRepository(self.session).get("asset_class_trading_enabled")
            try:
                enabled_map = _json.loads(raw_map) if raw_map else {}
            except (ValueError, TypeError):
                enabled_map = {}
            category = asset_class_trading_category(ctx.market.symbol)
            if is_asset_class_trading_blocked(category, enabled_map):
                opens_position = False
                agent_opinions_data.append({
                    "type": "gate_block",
                    "data": {
                        "gate": "asset_class_trading_gate",
                        "reason": "asset_class_disabled_by_user",
                        "asset_class": category,
                    },
                })

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

        # Faz 366 — kullanıcı isteği: "ürettiği strateji insan onayına
        # sunulur böyle bir yapı ayarlamıştık" — analytics/strategy_
        # hypothesis_scanner.py'nin (Faz 346) bulup services/strategy_
        # gate_proposer.py'nin insan onayına sunduğu (strateji, rejim)
        # adaylarından status="blocked" olanlar burada gerçekten
        # engelliyor. Faz 366-devam — kullanıcı bulgusu: "onaylı" kelimesi
        # yanlış okunuyordu ("onaylı strateji" = kazandıran strateji gibi
        # algılanabiliyordu) — onaylanan şey stratejinin iyiliği değil,
        # o rejimde ENGELLENMESİ, o yüzden durum "blocked"/"dismissed"
        # (bkz. StrategyGateApprovalRepository). trade_type (scalp/swing)
        # stop_loss_price'a bağlı olduğu için bu kapı stop_loss_price
        # hesaplandıktan SONRA çalışıyor — pyramid_regime_gate'in (entry_
        # price hesaplanır hesaplanmaz çalışan) AKSİNE, burada olmak
        # zorunda. İlk engellenen aday (2026-08-26, bu oturumda insan
        # kararıyla eklendi): ai_council_LONG_swing, bullish_high (win
        # %64.6 vs geri kalan %90.7, p=0.0, OOS'ta tekrarlandı).
        if opens_position and entry_price and experiment_bucket is None:
            from analytics.strategy_regime_gate import is_strategy_regime_gated
            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.repositories.strategy_gate_approval_repository import StrategyGateApprovalRepository
            from services.strategy_regime_compatibility_gatherer import _strategy_label

            settings_repo = AppSettingsRepository(self.session)
            if settings_repo.get("strategy_gate_enabled") == "true":
                features = ctx.market.features or {}
                trend = features.get("trend", "unknown")
                market_regime = (
                    f"{trend}_{features.get('volatility_regime', 'normal')}" if trend != "unknown" else None
                )
                strategy_label = _strategy_label(
                    experiment_bucket, direction, entry_price, stop_loss_price, agent_opinions_data,
                )
                blocked_pairs = StrategyGateApprovalRepository(self.session).list_blocked_pairs()
                if is_strategy_regime_gated(strategy_label, market_regime, blocked_pairs):
                    gate_data = {
                        "gate": "strategy_regime_gate",
                        "reason": "known_underperforming_strategy_regime_pair",
                        "strategy_label": strategy_label,
                        "market_regime": market_regime,
                    }
                    # Faz 397 (2026-09-01) — kullanıcı isteği: "strategy_
                    # gate_approvals bunlar test modunda işlem alımına
                    # engel olmasın ama" — bu kapı gerçek sermaye riskinde
                    # (canlı) hâlâ tam olarak engelliyor, ama test modunda
                    # (Faz 388'in "veri toplama hız kesmesin" ilkesiyle
                    # AYNI gerekçe) artık ENGELLEMİYOR — sadece şeffaf
                    # şekilde kaydediyor (canlıda engellerdi, ama test
                    # modunda değil).
                    if ctx.risk.trading_mode == "test":
                        agent_opinions_data.append({"type": "gate_bypassed_test_mode", "data": gate_data})
                    else:
                        opens_position = False
                        agent_opinions_data.append({"type": "gate_block", "data": gate_data})

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
                    leverage=leverage,
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

        # Faz 370-devam — bkz. contracts/decision_event.py'deki ilgili
        # alanların üstündeki not. Üçü de zaten hesaplanmış ara değerler —
        # burada sadece ayrı, sorgulanabilir sütunlara çıkarılıyor.
        council_direction = None
        council_confidence = None
        if debate_result is not None:
            debate_data = (
                debate_result.model_dump() if hasattr(debate_result, "model_dump") else debate_result
            )
            council_direction = debate_data.get("final_direction")
            council_confidence = debate_data.get("final_confidence")

        meta_decision = None
        pre_fusion_confidence = None
        if hasattr(ctx, "cognition"):
            for item in reversed(ctx.cognition.relevant_knowledge):
                if item.get("type") == "pre_fusion_snapshot":
                    meta_decision = item["data"].get("meta_decision")
                    pre_fusion_confidence = item["data"].get("pre_fusion_confidence")
                    break

        final_ev = None
        rejection_reason = None
        for entry in (decision_fusion_entries or []):
            if "rejection" in entry:
                rejection_reason = entry.get("rejection")
                final_ev = entry.get("ev")
                break

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
            council_direction=council_direction,
            council_confidence=council_confidence,
            meta_decision=meta_decision,
            pre_fusion_confidence=pre_fusion_confidence,
            final_ev=final_ev,
            rejection_reason=rejection_reason,
            mtf_direction=mtf_direction,
            mtf_confidence=mtf_confidence,
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
