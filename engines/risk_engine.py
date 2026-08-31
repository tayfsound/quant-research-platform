"""Risk Engine – tüm ret sebeplerini biriktirir, tek otorite."""
from contracts.context import CognitiveCycleContext
from contracts.contexts.risk import RiskReason
from observability.metrics import risk_decisions_total, risk_rejections_total


class RiskEngine:
    def __init__(self, secret: str = ""):
        self.secret = secret

    def _trip_kill_switch(self, consecutive_losses: int, threshold: int, cycle_id=None) -> None:
        """ai_enabled'ı GERÇEKTEN kalıcı olarak false'a çeker (app_settings'e
        yazar) — sadece bu cycle'ı reddetmek yeterli değil, aksi halde bir
        sonraki cycle aynı gerçek geçmişle yeniden hesaplayıp aynı sonuca
        varır ama arada bir insan hiç haberdar olmaz. Ayarı yazamazsa
        (DB erişilemez vb.) sessizce geçilir — bu cycle'ın kendi reddi
        (çağıran taraf) yine de uygulanır, fail-closed."""
        try:
            import structlog

            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.session_factory import SessionFactory

            with SessionFactory.get_session() as session:
                AppSettingsRepository(session).set(
                    "ai_enabled", "false", updated_by="kill_switch",
                )
                # Faz 269 (Cognitive Core 2.0 / M1) — Veri ve olay altyapısı:
                # bu olay şu ana kadar SADECE app_settings.updated_by
                # üzerinden dolaylı görülebiliyordu ("son değeri kim/ne
                # yazdı" — NE ZAMAN tetiklendiği, kaç kayıpla, bir önceki
                # tetiklenmeyle arada ne kadar geçtiği sorgulanamıyordu).
                # Faz 269-sonrası — distributed tracing: entity_id artık
                # position_opened/position_closed ile AYNI desen, hangi
                # cycle'ın (hangi kararın) bu switch'i tetiklediği DB'den
                # doğrudan sorgulanabilir.
                from database.repositories.event_log_repository import EventLogRepository

                EventLogRepository(session).record(
                    event_type="kill_switch_tripped",
                    entity_type="risk",
                    entity_id=cycle_id,
                    payload={"consecutive_losses": consecutive_losses, "threshold": threshold},
                )
            structlog.get_logger().error(
                "kill_switch_tripped",
                consecutive_losses=consecutive_losses,
                threshold=threshold,
            )
        except Exception:
            pass

    def execute(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        symbol = ctx.market.symbol or "unknown"

        # Faz 190: dashboard Start/Stop düğmesi — kapalıyken (test ya da live
        # fark etmez) yeni pozisyon açılmaz. Mevcut açık pozisyonlar
        # PositionCloser üzerinden tamamen bağımsız çalışmaya devam eder.
        if not ctx.risk.ai_enabled:
            ctx.risk.evaluation.verdict = "rejected"
            ctx.risk.evaluation.reasons = [RiskReason(
                code="AI_STOPPED",
                message="AI is stopped (dashboard Start/Stop) — no new positions",
                severity="info",
            )]
            risk_decisions_total.labels(verdict="rejected", symbol=symbol).inc()
            risk_rejections_total.labels(reason="AI_STOPPED").inc()
            return ctx

        # Kill switch — gerçek olay (2026-08-12): 24 saatte 102 ardışık
        # stop-loss, hiçbir otomatik durdurma yoktu, sadece manuel Start/
        # Stop vardı. Eşik aşıldığında (0 = devre dışı) SADECE bu cycle'ı
        # reddetmiyor — ai_enabled'ı GERÇEKTEN false'a çekip kalıcı olarak
        # durduruyor (dashboard'daki manuel düğmeyle AYNI etki), bir insan
        # tekrar açana kadar. Bir sonraki kazanan işlem otomatik sıfırlamaz
        # — "birkaç kazanç görülünce kendi kendine devam et" fail-fake
        # olurdu, gerçek bir insan gözden geçirmesi gerekiyor.
        if (
            ctx.risk.kill_switch_consecutive_losses > 0
            and ctx.risk.consecutive_losses >= ctx.risk.kill_switch_consecutive_losses
        ):
            self._trip_kill_switch(ctx.risk.consecutive_losses, ctx.risk.kill_switch_consecutive_losses, cycle_id=ctx.cycle_id)
            ctx.risk.ai_enabled = False
            ctx.risk.evaluation.verdict = "rejected"
            ctx.risk.evaluation.reasons = [RiskReason(
                code="CIRCUIT_BREAKER_CONSECUTIVE_LOSSES",
                message=(
                    f"{ctx.risk.consecutive_losses} ardışık kayıp >= "
                    f"{ctx.risk.kill_switch_consecutive_losses} eşiği — AI otomatik durduruldu, "
                    f"dashboard'dan manuel devam ettirilmeli"
                ),
                severity="critical",
            )]
            risk_decisions_total.labels(verdict="rejected", symbol=symbol).inc()
            risk_rejections_total.labels(reason="CIRCUIT_BREAKER_CONSECUTIVE_LOSSES").inc()
            return ctx

        # Faz 389 — kullanıcı isteği: min_seconds_between_trades cooldown
        # kontrolü (COOLDOWN_ACTIVE) kaldırıldı. Gerçek döngü süresi zaten
        # ~20-30dk'ya çıktığı için (104 sembol × multi-timeframe cascade),
        # kullanıcının manuel ayarladığı 60-300sn'lik değerler yapısal
        # olarak asla tetiklenemiyordu — anlamsız bir ayardı.

        # Faz 262 — kritik bulgu: Faz 188'in "test modunda ai sınırsız
        # takılabilsin" kararı (aşağıdaki bypass, artık kaldırıldı) kasa/
        # eşzamanlılık/drawdown kontrollerini test modunda TAMAMEN
        # atlıyordu. Pozisyonlar dakikalar içinde kapandığı eski rejimde
        # zararsızdı, ama Faz 261'in 1:4 hedef/stop oranı pozisyonların
        # günler/haftalar açık kalmasına yol açınca bu "sınırsız" kural
        # kontrolsüz birikmeye dönüştü — gerçek bulgu: kasa %15.9'a
        # (yapılandırılmış %5 limitin 3 katı üzerine) ulaşıp 1074 açık
        # pozisyon birikene kadar hiçbir kontrol devreye girmedi.
        # Kullanıcı kararı: test modu artık live modla AYNI kuralları
        # uyguluyor — "live'a geçince karşılaşacağımız sorunları şimdiden
        # görüp çözelim" gerekçesiyle. trading_mode hâlâ ayrı bir alan
        # (execution/exchange rotasını belirlemek için) ama risk kapısı
        # artık ona bakmıyor.
        limits = ctx.risk.limits
        proposed = ctx.decision.proposed_size
        reasons: list[RiskReason] = []

        # 1. Limit var mı?
        max_size_limit = limits.get("max_position_size")
        if max_size_limit is None:
            ctx.risk.evaluation.verdict = "rejected"
            ctx.risk.evaluation.reasons = [
                RiskReason(code="MISSING_LIMIT", message="No max_position_size limit defined", severity="critical")
            ]
            risk_decisions_total.labels(verdict="rejected", symbol=symbol).inc()
            risk_rejections_total.labels(reason="MISSING_LIMIT").inc()
            return ctx

        # 2. Hash doğru mu?
        if not max_size_limit.verify(self.secret):
            reasons.append(RiskReason(code="HASH_MISMATCH", message="Risk limit hash verification failed", severity="critical"))

        # 3. Pozisyon limiti aşıldı mı?
        # Faz 211: proposed artık ham "birim sayısı" değil, sermaye
        # bütçesinin güncel fiyata bölünmesiyle çıkan gerçek birim sayısı
        # (bkz. services/orchestrator.py::_build_context) — fiyata göre
        # kıyaslamak için max_position_size'ı ($ notional tavanı olarak)
        # proposed*price ile karşılaştırıyoruz. current_price yoksa (bazı
        # testler market verisi kurmuyor) eski ham karşılaştırmaya düşüyor
        # — geriye dönük uyumluluk için.
        current_price = (ctx.market.raw_snapshot or {}).get("close")
        proposed_notional = proposed * current_price if current_price else proposed
        limit_check_value = max_size_limit.value
        if proposed_notional > limit_check_value:
            reasons.append(RiskReason(
                code="SIZE_EXCEEDED",
                message=f"Size {proposed_notional} > limit {limit_check_value}",
                severity="warning",
            ))

        # 4. Drawdown limiti aşıldı mı?
        max_drawdown_limit = limits.get("max_drawdown")
        if max_drawdown_limit and ctx.risk.current_drawdown >= max_drawdown_limit.value:
            reasons.append(RiskReason(code="MAX_DRAWDOWN", message=f"Drawdown {ctx.risk.current_drawdown:.1%} >= {max_drawdown_limit.value:.1%}", severity="critical"))

        # 5. Aynı anda kaç pozisyon açık olabilir? (Faz 188, gerçek açık
        # pozisyon sayısı — bkz. services/risk_state.py)
        if ctx.risk.max_concurrent_positions is not None and ctx.risk.open_position_count >= ctx.risk.max_concurrent_positions:
            reasons.append(RiskReason(
                code="MAX_CONCURRENT_POSITIONS",
                message=f"{ctx.risk.open_position_count} open >= limit {ctx.risk.max_concurrent_positions}",
                severity="critical",
            ))

        # 6. Kasanın max %kaçı açık pozisyonlara bağlanmış olabilir?
        if ctx.risk.max_capital_pct is not None and ctx.risk.capital_used_pct >= ctx.risk.max_capital_pct:
            reasons.append(RiskReason(
                code="MAX_CAPITAL_PCT",
                message=f"{ctx.risk.capital_used_pct:.1%} used >= limit {ctx.risk.max_capital_pct:.1%}",
                severity="critical",
            ))

        # 7. Concept Drift — sistemin gerçek yakın-geçmiş kazanma oranı,
        # daha eski bir referans pencereye göre istatistiksel olarak
        # anlamlı VE büyük (>=15 puan) şekilde düştü mü? Hesaplama BURADA
        # DEĞİL, services/risk_state.py::load_position_risk_state()'te
        # yapılıyor (consecutive_losses ile AYNI desen) — RiskEngine'in
        # kendi içinde bir DB sorgusu yapması, test izolasyonunu bozan
        # gerçek bir regresyona yol açmıştı (bkz. o dosyadaki not).
        if ctx.risk.concept_drift_reason is not None:
            reasons.append(ctx.risk.concept_drift_reason)

        if reasons:
            ctx.risk.evaluation.verdict = "rejected"
            ctx.risk.evaluation.reasons = reasons
            risk_decisions_total.labels(verdict="rejected", symbol=symbol).inc()
            for r in reasons:
                risk_rejections_total.labels(reason=r.code).inc()
            return ctx

        # Onay
        factor = max(0.5, min(ctx.risk.adjustment.factor, 1.0))
        ctx.risk.evaluation.verdict = "approved"
        ctx.decision.risk_adjusted_size = proposed * factor
        risk_decisions_total.labels(verdict="approved", symbol=symbol).inc()
        return ctx
