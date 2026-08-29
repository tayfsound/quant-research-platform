"""Decision persistence — Phase 171 outcome support.

Faz 182: `decisions` became a TimescaleDB hypertable partitioned on
`timestamp` (faz161 migration), which requires the primary key to be
`(id, timestamp)` rather than `id` alone — Timescale won't allow a
standalone unique index on just `id` on a hypertable. ON CONFLICT below
matches that composite key. id+timestamp are both set once at DecisionEvent
construction, so retrying persist() on the same event still dedupes
correctly.
"""

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text

from contracts.decision_event import DecisionEvent
from observability.metrics import db_query_latency_seconds


class DecisionPersistor:
    def __init__(self, session):
        self.session = session

    def persist(self, event: DecisionEvent) -> None:
        with db_query_latency_seconds.labels(operation="decision_persist").time():
            self._persist(event)

    def _persist(self, event: DecisionEvent) -> None:
        contributions = list(event.agent_opinions) if event.agent_opinions else []

        if event.risk_evaluation:
            contributions.append({
                "type": "risk_evaluation",
                "data": event.risk_evaluation,
            })

        if event.market_snapshot:
            contributions.append({
                "type": "market_snapshot",
                "data": event.market_snapshot,
            })

        self.session.execute(
            text("""
                INSERT INTO decisions (
                    id,
                    timestamp,
                    symbol,
                    direction,
                    size,
                    confidence,
                    agent_contributions,
                    weight_snapshot_id,
                    belief_snapshot_id,
                    status,
                    outcome,
                    entry_price,
                    quantity,
                    opened_at,
                    stop_loss_price,
                    original_stop_loss_price,
                    take_profit_price,
                    leverage,
                    liquidation_price,
                    timeframe,
                    experiment_bucket,
                    execution_mode,
                    exchange_order_id,
                    exchange_client_order_id,
                    exchange_stop_order_id,
                    exchange_tp_order_id,
                    staged_entry_add_pending,
                    staged_entry_low_price,
                    council_direction,
                    council_confidence,
                    meta_decision,
                    pre_fusion_confidence,
                    final_ev,
                    rejection_reason,
                    mtf_direction,
                    mtf_confidence
                )
                VALUES (
                    :id,
                    :timestamp,
                    :symbol,
                    :direction,
                    :size,
                    :confidence,
                    CAST(:agent_contributions AS jsonb),
                    :weight_snapshot_id,
                    :belief_snapshot_id,
                    :status,
                    CAST(:outcome AS jsonb),
                    :entry_price,
                    :quantity,
                    :opened_at,
                    :stop_loss_price,
                    :stop_loss_price,
                    :take_profit_price,
                    :leverage,
                    :liquidation_price,
                    :timeframe,
                    :experiment_bucket,
                    :execution_mode,
                    :exchange_order_id,
                    :exchange_client_order_id,
                    :exchange_stop_order_id,
                    :exchange_tp_order_id,
                    :staged_entry_add_pending,
                    :staged_entry_low_price,
                    :council_direction,
                    :council_confidence,
                    :meta_decision,
                    :pre_fusion_confidence,
                    :final_ev,
                    :rejection_reason,
                    :mtf_direction,
                    :mtf_confidence
                )
                ON CONFLICT (id, timestamp) DO NOTHING
            """),
            {
                "id": str(event.id),
                "timestamp": event.timestamp,
                "symbol": event.symbol,
                "direction": event.proposed_direction or event.final_action or "WAIT",
                "size": event.final_size,
                "confidence": event.confidence,
                "agent_contributions": json.dumps(
                    contributions,
                    default=str,
                ),
                "weight_snapshot_id": (
                    str(event.weight_snapshot_id)
                    if event.weight_snapshot_id
                    else None
                ),
                "belief_snapshot_id": (
                    str(event.belief_snapshot_id)
                    if event.belief_snapshot_id
                    else None
                ),
                "status": event.status,
                "outcome": json.dumps(
                    event.outcome,
                    default=str,
                ) if event.outcome else None,
                "entry_price": event.entry_price,
                "quantity": event.quantity,
                "opened_at": event.opened_at,
                "stop_loss_price": event.stop_loss_price,
                "take_profit_price": event.take_profit_price,
                "leverage": event.leverage,
                "liquidation_price": event.liquidation_price,
                "timeframe": event.timeframe,
                "experiment_bucket": event.experiment_bucket,
                "execution_mode": event.execution_mode,
                "exchange_order_id": event.exchange_order_id,
                "exchange_client_order_id": event.exchange_client_order_id,
                "exchange_stop_order_id": event.exchange_stop_order_id,
                "exchange_tp_order_id": event.exchange_tp_order_id,
                "staged_entry_add_pending": event.staged_entry_add_pending,
                "staged_entry_low_price": event.staged_entry_low_price,
                "council_direction": event.council_direction,
                "council_confidence": event.council_confidence,
                "meta_decision": event.meta_decision,
                "pre_fusion_confidence": event.pre_fusion_confidence,
                "final_ev": event.final_ev,
                "rejection_reason": event.rejection_reason,
                "mtf_direction": event.mtf_direction,
                "mtf_confidence": event.mtf_confidence,
            },
        )

        self.session.commit()

        # Faz 269 event store devamı — kullanıcı isteği "Event sourcing":
        # sadece gerçekten açılmış (status="open") bir pozisyon bir olay
        # sayılır; no_trade/WAIT gürültü olur. Payload'da fiyat/miktar
        # tekrarlanmıyor, entity_id zaten decisions.id'ye işaret ediyor.
        if event.status == "open":
            from database.repositories.event_log_repository import EventLogRepository

            EventLogRepository(self.session).record(
                event_type="position_opened",
                entity_type="decision",
                entity_id=event.id,
                payload={"symbol": event.symbol, "direction": event.proposed_direction or event.final_action},
            )

    def get_by_id(self, decision_id: str):
        # Gerçek bulgu: geçersiz bir UUID string'i (örn. dashboard'dan yanlışlıkla
        # bir session_id yapıştırılırsa) Postgres'te "invalid input syntax for
        # type uuid" fırlatıyordu — yakalanmadan FastAPI'nin düz metin 500
        # sayfasına düşüyordu, dashboard bunu JSON sanıp parse hatası veriyordu.
        try:
            UUID(str(decision_id))
        except (ValueError, AttributeError, TypeError):
            return None

        row = self.session.execute(
            text("SELECT * FROM decisions WHERE id = :id"),
            {"id": decision_id},
        ).mappings().first()

        return dict(row) if row else None

    def get_last_opened_at(self, symbol: str):
        """Faz 189: bu sembol için en son gerçekten açılmış pozisyonun
        opened_at'i (open ya da closed, fark etmez) — cooldown kontrolü
        için. Hiç pozisyon açılmadıysa None."""
        row = self.session.execute(
            text(
                "SELECT opened_at FROM decisions "
                "WHERE symbol = :symbol AND opened_at IS NOT NULL "
                "ORDER BY opened_at DESC LIMIT 1"
            ),
            {"symbol": symbol},
        ).mappings().first()

        return row["opened_at"] if row else None

    def list_recent(self, limit: int = 100):
        rows = self.session.execute(
            text(
                "SELECT * FROM decisions ORDER BY timestamp DESC LIMIT :limit"
            ),
            {"limit": limit},
        ).mappings().all()

        return [dict(r) for r in rows]

    def get_by_symbol(self, symbol: str, limit: int = 100):
        rows = self.session.execute(
            text(
                "SELECT * FROM decisions WHERE symbol=:symbol ORDER BY timestamp DESC LIMIT :limit"
            ),
            {"symbol": symbol, "limit": limit},
        ).mappings().all()

        return [dict(r) for r in rows]

    def latest_direction_confidence_by_symbol(self, since=None) -> list[dict]:
        """Faz 362-devam — backlog madde 21 (kullanıcı isteği: "AI şu an
        piyasa yönünü nasıl görüyor" bilgi kartı). Her sembol için EN SON
        kararın (status'tan bağımsız — WAIT/no_trade dahil, council'in o
        anki HAM eğilimini yansıtır) direction/confidence/timestamp'i, tek
        sorguda (`DISTINCT ON`, Postgres'e özgü — 149 sembol için 149 ayrı
        sorgu yerine). `since` verilirse SADECE o zamandan sonraki kararlar
        dahil (stale/uzun süredir taranmayan sembolleri hariç tutmak için)."""
        params: dict = {}
        query = "SELECT DISTINCT ON (symbol) symbol, direction, confidence, timestamp FROM decisions "
        if since is not None:
            query += "WHERE timestamp >= :since "
            params["since"] = since
        query += "ORDER BY symbol, timestamp DESC"
        rows = self.session.execute(text(query), params).all()
        return [
            {"symbol": row.symbol, "direction": row.direction, "confidence": row.confidence, "timestamp": row.timestamp}
            for row in rows
        ]

    def list_recent_directions_for_symbol(self, symbol: str, limit: int = 20) -> list[dict]:
        """Faz 362 — analytics/signal_persistence.py::consistent_direction_
        run_length() için: bu sembol için en yeniden en eskiye doğru son
        `limit` kararın SADECE direction/timestamp'i (get_by_symbol'un
        SELECT * ağırlığı olmadan — bu kapı her yeni açılış adayında
        çalışıyor, ucuz kalmalı). Bu SIRA ile çağrıldığında (mevcut karar
        henüz persist edilmeden ÖNCE) doğal olarak "önceki" kararları
        döner, ayrı bir zaman filtresi gerekmez."""
        rows = self.session.execute(
            text(
                "SELECT direction FROM decisions WHERE symbol=:symbol "
                "ORDER BY timestamp DESC LIMIT :limit"
            ),
            {"symbol": symbol, "limit": limit},
        ).all()
        return [{"direction": row.direction} for row in rows]

    def list_recent_direction_confidence_for_symbol(
        self, symbol: str, limit: int = 20, since=None
    ) -> list[dict]:
        """Faz 362-devam — analytics/signal_persistence.py::consecutive_
        reversal_run_length() için: list_recent_directions_for_symbol ile
        AYNI, ama çıkış tetikleyicisinin ihtiyaç duyduğu confidence'ı da
        döner (giriş kapısı buna ihtiyaç duymuyordu, ayrı/daha hafif
        metod olarak bırakıldı). `since` verilirse (bkz. belief_reversal_
        exit.py — pozisyonun KENDİ opened_at'i) SADECE o pozisyon
        açıldıktan SONRAKİ kararlar döner — yoksa pozisyonun kendi açılış
        kaydı (aynı yön) en tepede çıkıp run'ı yanlışlıkla sıfırlar."""
        params = {"symbol": symbol, "limit": limit}
        query = "SELECT direction, confidence FROM decisions WHERE symbol=:symbol "
        if since is not None:
            query += "AND timestamp > :since "
            params["since"] = since
        query += "ORDER BY timestamp DESC LIMIT :limit"
        rows = self.session.execute(text(query), params).all()
        return [{"direction": row.direction, "confidence": row.confidence} for row in rows]

    def list_open_positions(self, limit: int | None = 200, offset: int = 0):
        # Faz 268y — kullanıcı bulgusu: 869 açık pozisyonun sadece ilk
        # 100'ünü (limit sabit, offset hiç yoktu) görebiliyordu, "diğerlerini
        # göremiyorum" — offset eklendi ki Transactions gerçek sayfalama
        # yapabilsin, tüm açık pozisyonlar (sadece en yeni 100'ü değil)
        # görülebilsin.
        #
        # Faz 269-sonrası — KRİTİK bulgu, kullanıcı raporuyla canlıda
        # yakalandı: services/position_closer.py::close_due_positions()
        # bu metodu HİÇ argüman vermeden (varsayılan limit=200) çağırıyordu
        # — ama sistemde GERÇEKTEN 2631 açık pozisyon vardı. ORDER BY
        # opened_at DESC LIMIT 200 yüzünden en eski ~2431 pozisyon
        # (GPSUSDT/TUTUSDT/HEMIUSDT/PORTALUSDT dahil — bazıları %20+
        # kârdaydı) close_due_positions'ın döngüsüne HİÇ girmiyordu:
        # stop/hedef/likidasyon/breakeven/trailing kontrolü SIFIR —
        # sonsuza kadar izlenmeden kalabilirlerdi. limit=None artık
        # LIMIT'i tamamen kaldırıyor — close_due_positions bunu kullanıyor.
        query = "SELECT * FROM decisions WHERE status = 'open' ORDER BY opened_at DESC"
        params: dict = {}
        if limit is not None:
            query += " LIMIT :limit OFFSET :offset"
            params = {"limit": limit, "offset": offset}
        rows = self.session.execute(text(query), params).mappings().all()

        return [dict(r) for r in rows]

    def open_notional_by_symbol(self) -> list[dict]:
        """Faz 268-sonrası — kullanıcı isteği: "orta-vadeli katmanı
        portföy VaR'ına dahil et... tam birleşik portföy VaR'ı." Kısa-
        vadeli VE orta-vadeli katmanlardaki (ayrı sermaye havuzu
        muhasebesinden bağımsız) TÜM gerçekten açık pozisyonları sembol
        bazında toplar — services/orchestrator.py::_apply_portfolio_
        fusion() artık SADECE bu cycle'ın eşzamanlı yeni önerilerine değil,
        GERÇEK mevcut portföy maruziyetine göre korelasyon/VaR hesaplıyor.
        Aynı sembolde hem LONG hem SHORT açık pozisyon varsa (hedge)
        net (birbirini götüren) maruziyet doğru olan — VaR gerçek net
        riski önemser, brüt pozisyon sayısını değil."""
        rows = self.session.execute(
            text("""
                SELECT symbol,
                    sum(
                        CASE WHEN direction = 'LONG' THEN entry_price * quantity
                             ELSE -(entry_price * quantity) END
                    ) AS signed_notional
                FROM decisions
                WHERE status = 'open' AND entry_price IS NOT NULL AND quantity IS NOT NULL
                GROUP BY symbol
            """)
        ).mappings().all()
        return [dict(r) for r in rows]

    def open_position_breakdown_by_trade_type(
        self, exclude_experiment_bucket: str | None = None
    ) -> list[dict]:
        """Faz 268-sonrası — kullanıcı isteği: "scalp, gün içi, orta vade
        vs. farklı işlem türlerinin ne kadarı short ne kadarı long
        pozisyonmuş" dashboard'da bir tabloda görünsün. api/rest/
        positions.py::_classify_trade_type() ile AYNI sınıflandırma
        mantığı — orada Python'da satır satır (agent_contributions JSONB'
        sinden hedge çıkarımı dahil) yapılıyor, burada 2457+ açık
        pozisyonun TAMAMINI Python'a çekip serialize etmek yerine (ağır)
        tek bir SQL agregasyonuyla aynı önceliklendirme sırasıyla
        (pump_fade > hedge > scalp/swing — Faz 317'de "gün içi" kovası,
        Faz 323'te "orta_vadeli" (timeframe'e bağımlı, kırılgan) kovası
        kaldırıldı) tekrarlanıyor — sonuç grup sayıları, tek tek pozisyon
        değil."""
        return self._breakdown_by_trade_type("open", exclude_experiment_bucket)

    def closed_trade_breakdown_by_trade_type(
        self, exclude_experiment_bucket: str | None = None
    ) -> list[dict]:
        """Kullanıcı isteği: "kapanmış işlemlerin olduğu kısıma ratioları
        eklememişsin oradaki bilgiye de ihtiyacım var" — açık pozisyonlar
        için yazılan open_position_breakdown_by_trade_type() ile AYNI
        agregasyon, sadece status='closed' üzerinde."""
        return self._breakdown_by_trade_type("closed", exclude_experiment_bucket)

    def _breakdown_by_trade_type(
        self, status: str, exclude_experiment_bucket: str | None = None
    ) -> list[dict]:
        # Faz 282 — kritik bulgu: bu agregasyon excluded_from_stats'ı hiç
        # kontrol etmiyordu — list_closed_trades/closed_trades_summary/
        # performance_by_period'ın (Faz 238'den beri) hepsi bilinen bug'
        # lardan kirlenmiş satırları hariç tutarken, bu tablo (dashboard'un
        # "işlem türüne göre long/short dağılımı" görünümü) hâlâ onları
        # sayıyordu — kullanıcı bulgusu: faz279/280/281'de excluded_from_
        # stats=true işaretlenen pump_fade/scalp/hedge satırları bu tabloda
        # hâlâ görünüyordu.
        query = """
                SELECT trade_type, direction, count(*) AS position_count
                FROM (
                    SELECT
                        direction,
                        CASE
                            WHEN experiment_bucket = 'pump_fade_v1' THEN 'pump_fade'
                            WHEN experiment_bucket = 'basis_arb_v1' THEN 'basis_arb'
                            WHEN EXISTS (
                                SELECT 1 FROM jsonb_array_elements(COALESCE(agent_contributions, '[]'::jsonb)) elem
                                WHERE elem->>'type' = 'market_snapshot'
                                  AND elem->'data'->'raw_snapshot'->>'pairs_trade' IS NOT NULL
                            ) THEN 'hedge'
                            WHEN entry_price IS NOT NULL AND stop_loss_price IS NOT NULL AND entry_price != 0 THEN
                                CASE
                                    WHEN abs(entry_price - stop_loss_price) / entry_price * 100 < 4.5 THEN 'scalp'
                                    ELSE 'swing'
                                END
                            ELSE NULL
                        END AS trade_type
                    FROM decisions
                    WHERE status = :status AND excluded_from_stats = false
                ) classified
                WHERE trade_type IS NOT NULL
                GROUP BY trade_type, direction
                ORDER BY trade_type, direction
            """
        params = {"status": status}
        if exclude_experiment_bucket is not None:
            query = query.replace(
                "WHERE status = :status AND excluded_from_stats = false",
                "WHERE status = :status AND excluded_from_stats = false "
                "AND (experiment_bucket IS NULL OR experiment_bucket != :exclude_experiment_bucket)",
            )
            params["exclude_experiment_bucket"] = exclude_experiment_bucket
        rows = self.session.execute(text(query), params).mappings().all()

        return [dict(r) for r in rows]

    def has_open_position_for_experiment(self, symbol: str, experiment_bucket: str) -> bool:
        """Faz 268-sonrası — kullanıcı isteği: pump-fade gibi AI konseyinden
        yalıtık, kendi experiment_bucket etiketiyle çalışan mekanik
        stratejiler için — aynı sembolde zaten kendi açık pozisyonu varken
        ikinci bir tane daha açmasın (count_open_by_symbol_direction AI'ın
        genel aynı-yön yığılma kontrolü, bu ondan bağımsız, TEK bir
        deneyin kendi sembolü için tekilliği)."""
        row = self.session.execute(
            text(
                "SELECT 1 FROM decisions WHERE status = 'open' "
                "AND symbol = :symbol AND experiment_bucket = :experiment_bucket LIMIT 1"
            ),
            {"symbol": symbol, "experiment_bucket": experiment_bucket},
        ).first()
        return row is not None

    def total_open_margin_for_experiment(self, experiment_bucket: str) -> float:
        """Faz 330 — kritik bulgu: pump_fade_strategy.py her yeni işlemi,
        o an o deneyde kaç pozisyon zaten açık olduğuna hiç bakmadan
        bağımsız olarak sermayenin bir yüzdesiyle (pump_fade_capital_pct)
        boyutlandırıyordu — kümülatif maruziyet hiç kontrol edilmiyordu.
        Gerçek veride yakalandı: 99 açık pump_fade pozisyonu, toplam GERÇEK
        marjin (notional/leverage) $2.21M — sermayenin ~%443'ü. entry_price*
        quantity NOTIONAL'dır (quantity zaten kaldıraçla çarpılmış,
        decision_recorder.py'deki AYNI desen) — marjine çevirmek için
        leverage'a bölünüyor (leverage NULL/0 ise, kaldıraçsız kabul edilip
        notional=marjin varsayılıyor, asla sıfıra bölme hatası değil)."""
        total = self.session.execute(
            text(
                "SELECT COALESCE(SUM(entry_price * quantity / NULLIF(leverage, 0)), 0) "
                "AS total_margin FROM decisions "
                "WHERE status = 'open' AND experiment_bucket = :experiment_bucket "
                "AND leverage IS NOT NULL AND leverage > 0"
            ),
            {"experiment_bucket": experiment_bucket},
        ).scalar()
        total_no_leverage = self.session.execute(
            text(
                "SELECT COALESCE(SUM(entry_price * quantity), 0) AS total_margin "
                "FROM decisions WHERE status = 'open' AND experiment_bucket = :experiment_bucket "
                "AND (leverage IS NULL OR leverage <= 0)"
            ),
            {"experiment_bucket": experiment_bucket},
        ).scalar()
        return float(total or 0.0) + float(total_no_leverage or 0.0)

    def count_open_positions_for_experiment(self, experiment_bucket: str) -> int:
        """Faz 332 — kritik bulgu: kümülatif MARJİN tavanı (Faz 330) tek
        başına yeterli değildi — 82-99 pozisyonun aynı anda, çoğunlukla
        AYNI yönde (SHORT) ve yüksek korelasyonlu (hepsi 'pump' etiketli
        altcoin) açık olması, tek bir piyasa rejiminin (genel yükseliş)
        TÜM pozisyonları aynı anda vurmasına yol açtı — bu bir
        çeşitlendirme başarısızlığı, marjin miktarından bağımsız bir
        risk boyutu. Ayrı bir tavan (pump_fade_max_open_positions) bu
        sayıyı da sınırlıyor."""
        count = self.session.execute(
            text(
                "SELECT count(*) FROM decisions "
                "WHERE status = 'open' AND experiment_bucket = :experiment_bucket"
            ),
            {"experiment_bucket": experiment_bucket},
        ).scalar()
        return int(count or 0)

    def mark_staged_entry_added(self, decision_id: str) -> None:
        """Faz 364 — pump_fade Kademeli Giriş: ekleme (add) bacağı
        başarıyla açıldıktan sonra ilk bacağın staged_entry_add_pending'i
        False'a çekilir — aynı olay için bir daha asla eklenmesin diye."""
        self.session.execute(
            text("UPDATE decisions SET staged_entry_add_pending = false WHERE id = :id"),
            {"id": decision_id},
        )
        self.session.commit()

    def list_open_positions_for_experiment(self, experiment_bucket: str) -> list[dict]:
        """Faz 344 — Cross-Asset Arbitrage Engine'in çift-bacaklı (aynı
        sembol, LONG spot + SHORT perpetual) pozisyonlarını BİRLİKTE
        kapatabilmesi için: bu experiment_bucket'taki TÜM açık pozisyonlar
        (limit'siz — pairs_trader/pump_fade'in list_open_positions(limit=
        None) ile AYNI ilke, hiçbir bacak sessizce gözden kaçmasın)."""
        rows = self.session.execute(
            text(
                "SELECT * FROM decisions "
                "WHERE status = 'open' AND experiment_bucket = :experiment_bucket "
                "ORDER BY opened_at ASC"
            ),
            {"experiment_bucket": experiment_bucket},
        ).mappings().all()
        return [dict(r) for r in rows]

    def close_and_exclude_from_stats(
        self,
        decision_id: str,
        *,
        exit_price: float,
        pnl: float,
        closed_at,
        outcome: dict | None = None,
        exit_reason: str = "legacy_cleanup",
    ) -> bool:
        """Faz 279/2026-08-28 — geçmişte açık kalmış pump_fade_v1 pozisyonları
        temizlenirken, açılan gerçek veri ayrı bir kategoride kalmalı; kapatma
        işlemi sadece kapatmaz, aynı anda istatistiklerden de çıkarılır. Burada
        satır silinmez, event sourcing korunur; sadece status='closed',
        excluded_from_stats=true işaretlenir ve kapanış bilgisi yazılır."""
        result = self.session.execute(
            text("""
                UPDATE decisions
                SET
                    status = 'closed',
                    exit_price = :exit_price,
                    pnl = :pnl,
                    closed_at = :closed_at,
                    outcome = CAST(:outcome AS jsonb),
                    excluded_from_stats = true,
                    market_regime = COALESCE(market_regime, 'legacy_cleanup')
                WHERE id = :id AND status = 'open'
            """),
            {
                "id": decision_id,
                "exit_price": exit_price,
                "pnl": pnl,
                "closed_at": closed_at,
                "outcome": json.dumps({**(outcome or {}), "exit_reason": exit_reason}, default=str),
            },
        )
        self.session.commit()
        return result.rowcount > 0

    def close_stale_positions_for_experiment(
        self,
        experiment_bucket: str,
        cutoff_at,
        current_prices: dict[str, float] | None = None,
        exit_reason: str = "legacy_cleanup",
    ) -> list[dict]:
        """Bu deneyin, verilen tarih öncesinden kalan açık pozisyonlarını
        mevcut fiyatlarına göre kapatıp istatistiklerden çıkartır. Sadece
        status='open' ve experiment_bucket uyumlu satırlar işlenir; bu
        operasyon salt temizleme amacı taşıdığı için kapatma sonucu detayını
        döndürür."""
        rows = self.session.execute(
            text(
                "SELECT * FROM decisions "
                "WHERE status = 'open' AND experiment_bucket = :experiment_bucket "
                "AND opened_at IS NOT NULL AND opened_at < :cutoff_at "
                "ORDER BY opened_at ASC"
            ),
            {"experiment_bucket": experiment_bucket, "cutoff_at": cutoff_at},
        ).mappings().all()

        if not rows:
            return []

        if current_prices is None:
            from services.position_closer import fetch_current_prices_by_symbol

            current_prices = fetch_current_prices_by_symbol({row["symbol"] for row in rows})

        closed: list[dict] = []
        for row in rows:
            symbol = row["symbol"]
            exit_price = current_prices.get(symbol)
            if exit_price is None or exit_price <= 0:
                continue

            entry_price = row.get("entry_price")
            quantity = float(row.get("quantity") or 0.0)
            if entry_price is None or quantity <= 0:
                continue

            direction = (row.get("direction") or "").upper()
            if direction == "LONG":
                pnl = (exit_price - entry_price) * quantity
            elif direction == "SHORT":
                pnl = (entry_price - exit_price) * quantity
            else:
                pnl = 0.0

            outcome = {
                "exit_reason": exit_reason,
                "closed_via": "legacy_cleanup",
                "entry_price": entry_price,
                "exit_price": exit_price,
                "quantity": quantity,
                "gross_pnl": pnl,
                "excluded_from_stats": True,
            }
            if self.close_and_exclude_from_stats(
                str(row["id"]),
                exit_price=exit_price,
                pnl=pnl,
                closed_at=row.get("closed_at") or datetime.now(UTC),
                outcome=outcome,
                exit_reason=exit_reason,
            ):
                closed.append({
                    "decision_id": str(row["id"]),
                    "symbol": symbol,
                    "direction": direction,
                    "exit_price": exit_price,
                    "pnl": pnl,
                    "opened_at": row.get("opened_at").isoformat() if row.get("opened_at") else None,
                })

        return closed

    def total_pnl_for_experiment(self, experiment_bucket: str, min_opened_at=None) -> float:
        """Faz 332 — pump_fade'in zarar-bazlı devre kesicisi için: SADECE
        gerçekleşmiş (kapanmış, excluded_from_stats hariç) kâr/zarar.
        Gerçekleşmemiş (açık pozisyonların anlık mark-to-market) zarar
        BİLEREK buraya dahil değil — canlı fiyat sorgusu gerektirir,
        pahalı/yavaş olur ve run_cycle'ın her tetiklenişinde (dakikada
        bir) çalıştırmak gerçekçi değil; gerçekleşmiş zarar zaten
        kalıcı/geri dönüşsüz bir sinyal, devre kesici için yeterli.

        Faz 364 — min_opened_at: services/risk_state.py'nin kill_switch_
        legacy_cutoff_at'ıyla AYNI desen. Gerçek olay (2026-08-26): Faz
        332 krizinin 20 Ağustos'ta açılmış ~82 legacy pozisyonu (o zamanki
        BOZUK, tavansız boyutlandırma formülüyle) günler sonra teker teker
        kapanmaya devam edip devre kesiciyi (-$269K) kalıcı olarak
        tetiklenmiş bıraktı — düzeltmeden SONRA açılan hiçbir yeni pozisyon
        yokken bile. min_opened_at set edilirse, bu tarihten ÖNCE açılmış
        pozisyonlar toplama HİÇ girmez — dashboard/istatistikler (bu
        parametreyi hiç geçmeyen çağıranlar) etkilenmez, o pozisyonlar hâlâ
        gerçek ve hâlâ sayılıyor, sadece devre kesici artık GÜNCEL
        performansa bakıyor."""
        query = (
            "SELECT COALESCE(SUM(pnl), 0) FROM decisions "
            "WHERE status = 'closed' AND excluded_from_stats = false "
            "AND experiment_bucket = :experiment_bucket"
        )
        params: dict = {"experiment_bucket": experiment_bucket}
        if min_opened_at is not None:
            query += " AND opened_at IS NOT NULL AND opened_at >= :min_opened_at"
            params["min_opened_at"] = min_opened_at
        total = self.session.execute(text(query), params).scalar()
        return float(total or 0.0)

    def symbols_with_last_exit_reason_stop_loss(self, symbols: list[str], experiment_bucket: str) -> set[str]:
        """Faz 341 — pump_fade'in stop-sonrası tekrar-giriş sıkılaştırması
        için: verilen sembollerden, o experiment_bucket'taki EN SON kapanan
        işlemi stop_loss ile bitenlerin kümesi. exit_reason gerçek bir sütun
        DEĞİL, outcome jsonb'sinin bir alanı (closed_trades_summary() ile
        AYNI okuma deseni). DISTINCT ON (Postgres) — her sembol için sadece
        en yeni closed_at'li satır, tek sorgu."""
        if not symbols:
            return set()
        rows = self.session.execute(
            text(
                "SELECT symbol, exit_reason FROM ("
                "  SELECT DISTINCT ON (symbol) symbol, outcome ->> 'exit_reason' AS exit_reason "
                "  FROM decisions "
                "  WHERE status = 'closed' AND experiment_bucket = :experiment_bucket "
                "  AND symbol = ANY(:symbols) "
                "  ORDER BY symbol, closed_at DESC"
                ") last_per_symbol WHERE exit_reason = 'stop_loss'"
            ),
            {"experiment_bucket": experiment_bucket, "symbols": symbols},
        ).fetchall()
        return {r.symbol for r in rows}

    def count_open_by_symbol_direction(self, symbol: str) -> dict[str, int]:
        """Faz 268-sonrası — bkz. contracts/contexts/risk.py::
        same_direction_open_counts. Bu SEMBOL için, yöne göre gruplanmış
        ŞU AN açık pozisyon sayısı — RiskGateStage'in aynı sembol/yönde
        sınırsız yığılmayı (gerçek olay: XAUTUSDT SHORT x54) engelleyen
        kontrolü için."""
        rows = self.session.execute(
            text(
                "SELECT direction, count(*) AS n FROM decisions "
                "WHERE status = 'open' AND symbol = :symbol AND direction IN ('LONG','SHORT') "
                "GROUP BY direction"
            ),
            {"symbol": symbol},
        ).all()
        return {row.direction: row.n for row in rows}

    def sum_open_notional_by_symbol_direction(self, symbol: str) -> dict[str, float]:
        """Faz 358 — kullanıcı bulgusu: count_open_by_symbol_direction
        SADECE pozisyon SAYISINI görüyor, kaç $ bağlı olduğunu değil — aynı
        sembolde art arda büyüyen boyutlarla (piramitleme) açılan az sayıda
        ama devasa pozisyon bu sayaçtan hiç geçmez. Bu, GERÇEK bağlı
        marjini (kaldıraçtan bağımsız — entry_price*quantity/leverage,
        risk_state.py::capital_used_pct ile AYNI formül) yön bazında
        toplar — RiskGateStage'in MAX_SAME_SYMBOL_DIRECTION_CAPITAL_PCT
        kontrolü için."""
        rows = self.session.execute(
            text(
                "SELECT direction, "
                "sum(entry_price * quantity / COALESCE(NULLIF(leverage, 0), 1.0)) AS notional "
                "FROM decisions "
                "WHERE status = 'open' AND symbol = :symbol AND direction IN ('LONG','SHORT') "
                "AND entry_price IS NOT NULL AND quantity IS NOT NULL "
                "GROUP BY direction"
            ),
            {"symbol": symbol},
        ).all()
        return {row.direction: float(row.notional or 0.0) for row in rows}

    def avg_open_entry_price_by_symbol_direction(self, symbol: str) -> dict[str, float]:
        """Faz 361 — analytics/pyramid_regime_gate.py::is_worse_price_
        pyramid_blocked() için: bu sembol/yönde ZATEN açık pozisyonların
        ortalama giriş fiyatı. Yeni bir girişin bu ortalamaya göre "daha
        kötü fiyattan" olup olmadığını (piramitleme + tepeden giriş)
        anlamak için — sum_open_notional_by_symbol_direction ile AYNI
        WHERE deseni, farklı agregasyon (AVG, SUM değil)."""
        rows = self.session.execute(
            text(
                "SELECT direction, avg(entry_price) AS avg_entry_price "
                "FROM decisions "
                "WHERE status = 'open' AND symbol = :symbol AND direction IN ('LONG','SHORT') "
                "AND entry_price IS NOT NULL "
                "GROUP BY direction"
            ),
            {"symbol": symbol},
        ).all()
        return {row.direction: float(row.avg_entry_price) for row in rows}

    def open_positions_summary(self) -> dict:
        """Faz 262 — Faz 224'ün kapanmış işlemler için çözdüğü AYNI bug,
        açık pozisyonlarda hâlâ vardı: GET /positions'ın döndürdüğü liste
        limit=100'e sabitliydi, dashboard'daki "Açık pozisyon" sayacı da bu
        listenin uzunluğunu (open.length) gösteriyordu — gerçek açık
        pozisyon sayısı 100'ü geçtiği anda ekran hep "100"de donuyordu,
        gerçek (ve büyümeye devam eden) sayıyı hiç yansıtmıyordu. Kullanıcı
        bulgusu: "iki gün önceki gibi hâlâ 100 görünüyor" — gerçek sayı bu
        sırada 1074'tü. TABLOYU limitlemeden, gerçek toplam üzerinden tek
        bir SQL agregasyonu."""
        row = self.session.execute(
            text(
                "SELECT count(*) AS open_count, "
                "sum(entry_price * quantity) AS committed_notional "
                "FROM decisions WHERE status = 'open'"
            )
        ).mappings().one()
        return {
            "open_count": row["open_count"] or 0,
            "committed_notional": float(row["committed_notional"] or 0.0),
        }

    def list_closed_trades(
        self, limit: int | None = 200, min_opened_at=None, exclude_experiment_bucket: str | None = None,
        direction: str | None = None, offset: int = 0,
    ):
        # Faz 238: kullanıcı isteği — "kirli geçmiş veriyi temizle."
        # excluded_from_stats=true işaretli satırlar (aşırı capital
        # testlerinden kalan, gerçek olmayan notional'lı işlemler)
        # varsayılan olarak dışarıda bırakılıyor — silinmiyor, sadece
        # normal görünümden hariç tutuluyor.
        #
        # Faz 268-sonrası: min_opened_at — SADECE kill switch'in ardışık-
        # kayıp sayacı (bkz. services/risk_state.py) kullanıyor, dashboard
        # istatistikleri (closed_trades_summary) bu parametreyi hiç
        # geçmiyor. opened_at NULL olan (çok eski, bu alan eklenmeden
        # önceki) satırlar filtre aktifken YOK sayılır — yaşı
        # doğrulanamayan bir işlem "taze" varsayılmaz (fail-closed).
        #
        # Faz 268-sonrası: exclude_experiment_bucket — SADECE kill switch'in
        # ardışık-kayıp sayacı VE Concept Drift (bkz. risk_state.py) bunu
        # pump_fade_v1 için kullanıyor. Kullanıcı isteği: pump-fade AI karar/
        # confidence sisteminden tamamen yalıtık olmalı — bu satır olmadan,
        # pump-fade'in kendi (AI'dan çok farklı bir kâr/zarar dağılımına
        # sahip) kapanışları AI'ın kill switch'ini/concept drift algısını
        # kirletir, mekanik bir strateji AI'ı sessizce durdurabilirdi.
        query = "SELECT * FROM decisions WHERE status = 'closed' AND excluded_from_stats = false"
        params: dict = {"limit": limit, "offset": offset}
        # Faz 363 — kullanıcı bulgusu: opportunity_quality_gatherer.py'nin
        # sabit limit=2000'i, nadir-olay (yüksek konsensüs) tespiti için
        # en eski %39'luk veriyi (1264/3264 işlem) hiç görmüyordu — kullanıcı
        # isteği "yapabildiğin kadar geniş yap" — list_open_positions'ın
        # (Faz 269-sonrası) limit=None desenini burada da kullanıma açıyoruz.
        if min_opened_at is not None:
            query += " AND opened_at IS NOT NULL AND opened_at >= :min_opened_at"
            params["min_opened_at"] = min_opened_at
        if exclude_experiment_bucket is not None:
            query += " AND (experiment_bucket IS NULL OR experiment_bucket != :exclude_experiment_bucket)"
            params["exclude_experiment_bucket"] = exclude_experiment_bucket
        if direction is not None:
            # Faz 352 — Regime Reversal Guardian: YÖN-bazlı ardışık stop
            # sayacı, kill switch'in GLOBAL sayacının aksine tek bir yönün
            # (LONG ya da SHORT) kendi geçmişine bakmalı — diğer yönün
            # kapanışları araya girip streak'i sulandırmasın.
            query += " AND direction = :direction"
            params["direction"] = direction
        # Faz 362-devam — kullanıcı isteği: "kör gidiyorum, geriye dönüp
        # inceleme yapamıyorum" (Transactions'ta kapanmış işlemler hep
        # ilk 100'le sabitliydi, offset yoktu) — list_open_positions'ın
        # Faz 268y'de aldığı offset desteğiyle AYNI desen.
        query += " ORDER BY closed_at DESC"
        if limit is not None:
            query += " LIMIT :limit OFFSET :offset"
        else:
            params.pop("limit", None)
            params.pop("offset", None)

        rows = self.session.execute(text(query), params).mappings().all()

        return [dict(r) for r in rows]

    def closed_trades_summary(self, exclude_experiment_bucket: str | None = None) -> dict:
        """Faz 224: kritik bulgu — kullanıcı: "sürekli işlem alıyor kapatıyor
        ama kapanmış işlem sayısı 100 görünüyor, bir ara 400 küsürdü... bu
        dashboarda güvenemiyorum." Kök neden: GET /trades'in summary'si
        (count/win_rate/total_pnl) list_closed_trades(limit=100)'ün
        DÖNDÜRDÜĞÜ dilimden hesaplanıyordu — yani toplam kapanmış işlem
        sayısı 100'ü geçtiği anda "count" hep tam 100'de donuyor, gerçek
        toplamı hiç yansıtmıyordu. Performance sayfası ise limit=10000 ile
        (gerçeğe daha yakın ama o da bir tavan) ayrı bir hesap yapıyordu —
        aynı isimli iki sayı farklı gerçek kümelerden geliyordu. Bu metod
        TABLOYU limitlemeden, gerçek toplam üzerinden tek bir SQL
        agregasyonuyla hesaplıyor — hem /trades hem /performance artık
        AYNI, gerçek toplamı kullanabilir.

        `exclude_experiment_bucket`, dashboard'un sadece AI council / production
        katmanını saymasını sağlamak için opsiyonel olarak kullanılır. Bu, satırları
        silmez; sadece o mekanik deneyin (ör. pump_fade_v1) istatistiklere karışmasını
        engeller."""
        # Faz 238: excluded_from_stats=true işaretli (kirli/aşırı-test)
        # satırlar agregata hiç girmiyor.
        #
        # Faz 268ah — kullanıcı bulgusu: "ROI konusunda problem olduğundan
        # şüpheliyim, pozisyon büyüklükleri ilişkisi kaotik." Gerçek bug:
        # DecisionRecorder kaldıraçlı pozisyonlarda quantity'yi zaten
        # leverage ile çarpıyor (Faz 255) — yani entry_price*quantity
        # GERÇEK yatırılan marjin değil, kaldıraçlı TAM notional. Kapanmış
        # işlemlerde doğrulandı: mevcut hesap $419k notional gösteriyordu,
        # gerçek marjin sadece $33.8k (12.4x fark) — sembol başına farklı
        # kaldıraç (1x/5x/10x/25x) notional'ı orantısız şişiriyordu, ROI'yi
        # kaotik/anlamsız kılan tam olarak buydu. deployed_notional artık
        # gerçek marjini (notional/leverage) topluyor.
        query = (
            "SELECT count(*) AS trade_count, "
            "sum(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins, "
            "sum(pnl) AS total_pnl, "
            "sum(entry_price * quantity / COALESCE(NULLIF(leverage, 0), 1)) AS deployed_notional, "
            # Faz 268-sonrası — kullanıcı isteği: manuel kapatılan
            # işlemler (exit_reason='manual_full' — genelde sinyal
            # tersine döndüğü için sistemin erken kapattığı işlemler)
            # ayrı bir "manuel" kovasında gösterilmesin, kârlıysa TP
            # gibi, zarardaysa SL gibi sayılsın — kapanış MEKANİZMASI
            # değil, GERÇEK sonuç (kâr/zarar) önemli.
            # Faz 291 — kullanıcı bulgusu (gerçek CHIPUSDT örneği):
            # trailing_stop_profit (bkz. position_closer.py) da GERÇEK
            # bir kâr kapanışı — mekanizması "stop" ama sonucu "hedef"
            # gibi, aynı manual_full ilkesiyle burada da TP sayılıyor.
            "sum(CASE WHEN outcome ->> 'exit_reason' IN ('take_profit', 'trailing_stop_profit') "
            "OR (outcome ->> 'exit_reason' = 'manual_full' AND pnl > 0) THEN 1 ELSE 0 END) AS tp_count, "
            "sum(CASE WHEN outcome ->> 'exit_reason' = 'stop_loss' "
            "OR (outcome ->> 'exit_reason' = 'manual_full' AND pnl <= 0) THEN 1 ELSE 0 END) AS sl_count, "
            # manual_partial SADECE status='open' kalan (miktarı
            # azaltılmış) satırlarda görülür — closed satırlarda hiç
            # oluşmaz, bu yüzden closed özetinde manual_count her
            # zaman 0'a yakınsar (bkz. position_closer.py).
            "sum(CASE WHEN outcome ->> 'exit_reason' = 'manual_partial' THEN 1 ELSE 0 END) AS manual_count, "
            # Faz 311 — kullanıcı isteği (uzun süredir bekleyen todo):
            # "toplam manuel kapanan işlem" kartı. manual_count'un
            # (yukarıda) AYRI ve neredeyse hep sıfır olan manual_partial
            # ile karıştırılmaması için AYRI bir alan — kullanıcının
            # ELLE tamamen kapattığı (manual_full) işlemlerin GERÇEK
            # toplam sayısı, sonucundan (kâr/zarar) BAĞIMSIZ. tp_count/
            # sl_count'un manual_full'u sonucuna göre kendi içine
            # katması (yukarıdaki Faz 268-sonrası ilkesi) DEĞİŞMİYOR —
            # bu SADECE ek, bilgilendirici bir toplam.
            "sum(CASE WHEN outcome ->> 'exit_reason' = 'manual_full' THEN 1 ELSE 0 END) AS manual_full_count "
            "FROM decisions WHERE status = 'closed' AND excluded_from_stats = false"
        )
        params: dict = {}
        if exclude_experiment_bucket is not None:
            query += " AND (experiment_bucket IS NULL OR experiment_bucket != :exclude_experiment_bucket)"
            params["exclude_experiment_bucket"] = exclude_experiment_bucket
        row = self.session.execute(text(query), params).mappings().one()
        excluded_count = self.session.execute(
            text(
                "SELECT count(*) FROM decisions WHERE status = 'closed' AND excluded_from_stats = true "
                "AND (:exclude_experiment_bucket IS NULL OR experiment_bucket != :exclude_experiment_bucket)"
            ),
            {"exclude_experiment_bucket": exclude_experiment_bucket},
        ).scalar()
        trade_count = row["trade_count"] or 0
        return {
            "trade_count": trade_count,
            "win_rate": (row["wins"] / trade_count) if trade_count else 0.0,
            "total_pnl": float(row["total_pnl"] or 0.0),
            "deployed_notional": float(row["deployed_notional"] or 0.0),
            "excluded_count": excluded_count or 0,
            "tp_count": row["tp_count"] or 0,
            "sl_count": row["sl_count"] or 0,
            "manual_count": row["manual_count"] or 0,
            "manual_full_count": row["manual_full_count"] or 0,
        }

    def closed_trades_summary_by_direction(
        self, exclude_experiment_bucket: str | None = None
    ) -> dict:
        """Faz 322 — kullanıcı isteği: "genel toplamda long/short kazanma
        oranı" — Dashboard'da hiçbir yerde LONG'un mu SHORT'un mu daha
        başarılı olduğu görünmüyordu. closed_trades_summary() ile AYNI
        kapsam (status='closed' AND excluded_from_stats=false — pump_fade
        DAHİL, mevcut "Kazanma oranı" kartıyla AYNI kural, tutarlılık
        için ayrı bir filtre icat edilmiyor), sadece direction'a göre
        gruplanmış."""
        query = (
            "SELECT direction, count(*) AS trade_count, "
            "sum(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins "
            "FROM decisions WHERE status = 'closed' AND excluded_from_stats = false "
            "AND direction IN ('LONG', 'SHORT')"
        )
        params: dict = {}
        if exclude_experiment_bucket is not None:
            query += " AND (experiment_bucket IS NULL OR experiment_bucket != :exclude_experiment_bucket)"
            params["exclude_experiment_bucket"] = exclude_experiment_bucket
        query += " GROUP BY direction"
        rows = self.session.execute(text(query), params).mappings().all()
        result = {
            "LONG": {"trade_count": 0, "win_count": 0, "loss_count": 0, "win_rate": 0.0},
            "SHORT": {"trade_count": 0, "win_count": 0, "loss_count": 0, "win_rate": 0.0},
        }
        for r in rows:
            trade_count = r["trade_count"] or 0
            win_count = r["wins"] or 0
            result[r["direction"]] = {
                "trade_count": trade_count,
                "win_count": win_count,
                "loss_count": trade_count - win_count,
                "win_rate": (win_count / trade_count) if trade_count else 0.0,
            }
        return result

    # Faz 268-sonrası: kullanıcı bulgusu — bir gün için hiç GERÇEK (excluded_
    # from_stats=false) kapanış yoksa (o gün hiç işlem olmadığı için ya da
    # o günün tamamı hariç tutulduğu için) date_trunc/GROUP BY o kovayı hiç
    # ÜRETMİYORDU — gün sessizce listeden düşüyordu, "0 işlem" olarak değil.
    # Kullanıcının kendi sözü: "Veri yoksa o gün veri yok olarak görünmesi
    # lazım, gün atlaması normal değil." generate_series ile bugünden geriye
    # doğru KESİKSİZ bir kova serisi kuruluyor, gerçek veri LEFT JOIN'le
    # üstüne biniyor — veri olmayan kovalar artık 0 ile açıkça görünüyor.
    _PERIOD_TO_INTERVAL = {"day": "1 day", "week": "1 week", "month": "1 month", "year": "1 year"}

    def performance_by_period(self, period: str, limit: int = 200, exclude_experiment_bucket: str | None = None) -> list[dict]:
        """Faz 215: kullanıcı isteği — "dün ne kadar ROI yapmış, haftalık/
        aylık/yıllık ne olmuş" dashboard'da hiç görünmüyordu. period:
        Postgres date_trunc'ın kabul ettiği bir değer (day/week/month/year).
        Her kova için gerçek kapanmış işlemlerden pnl toplamı/işlem
        sayısı/win rate — icat edilmiş bir sayı değil. Veri olmayan kovalar
        da (yukarıdaki not) artık kesiksiz döner, sessizce atlanmaz.

        `exclude_experiment_bucket` opsiyonel olarak verilir; örn. pump_fade_v1
        gibi mekanik deneyler sadece dashboard'ı kirletmesin diye dışarıda tutulur."""
        if period not in ("day", "week", "month", "year"):
            raise ValueError(f"invalid period: {period}")
        interval = self._PERIOD_TO_INTERVAL[period]
        params = {"limit": limit}
        query = f"""
                WITH real_data AS (
                    SELECT
                        date_trunc('{period}', closed_at) AS bucket,
                        count(*) AS trade_count,
                        sum(pnl) AS total_pnl,
                        sum(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
                        sum(entry_price * quantity / COALESCE(NULLIF(leverage, 0), 1)) AS deployed_notional
                    FROM decisions
                    WHERE status = 'closed' AND closed_at IS NOT NULL AND excluded_from_stats = false
                """
        if exclude_experiment_bucket is not None:
            query += " AND (experiment_bucket IS NULL OR experiment_bucket != :exclude_experiment_bucket)"
            params["exclude_experiment_bucket"] = exclude_experiment_bucket
        query += f"""
                    GROUP BY bucket
                ),
                buckets AS (
                    SELECT generate_series(
                        date_trunc('{period}', now()) - (:limit - 1) * interval '{interval}',
                        date_trunc('{period}', now()),
                        interval '{interval}'
                    ) AS bucket
                )
                SELECT
                    b.bucket AS bucket,
                    COALESCE(r.trade_count, 0) AS trade_count,
                    COALESCE(r.total_pnl, 0) AS total_pnl,
                    COALESCE(r.wins, 0) AS wins,
                    COALESCE(r.deployed_notional, 0) AS deployed_notional
                FROM buckets b
                LEFT JOIN real_data r ON r.bucket = b.bucket
                ORDER BY b.bucket DESC
            """
        rows = self.session.execute(text(query), params).mappings().all()

        return [dict(r) for r in rows]

    def close_position(
        self,
        decision_id: str,
        exit_price: float,
        pnl: float,
        closed_at,
        outcome: dict | None = None,
        market_regime: str | None = None,
    ) -> bool:
        """Faz 360 — kullanıcı onayıyla eklenen gerçek-zamanlı (WebSocket)
        kapatma yolu, mevcut periyodik (REST) yolla AYNI pozisyonu
        eşzamanlı görebilir hale geldi (ör. fiyat hem tick'te hem bir
        sonraki 60sn'lik REST taramasında stop'u geçmiş görünebilir).
        WHERE'e SADECE bu satırın hâlâ 'open' olduğu şartı eklendi ve
        rowcount kontrol ediliyor — daha önce bu kontrol hiç yoktu, iki
        eşzamanlı çağrı birbirinin exit_price/pnl'ini SESSİZCE ezebilirdi.
        False dönerse (0 satır etkilendi) çağıran taraf pozisyonun zaten
        BAŞKA bir yoldan kapatıldığını anlar, kendi öğrenme/hafıza
        adımlarını (ikinci kez) tekrarlamamalı."""
        # Faz 244-246: market_regime verilmezse (ya da "unknown") sütun
        # NULL kalır — icat edilmiş bir rejim atanmaz, Predictive Risk
        # Monte Carlo'su sadece GERÇEKTEN etiketlenmiş kapanışları kullanır.
        result = self.session.execute(
            text("""
                UPDATE decisions
                SET
                    status = 'closed',
                    exit_price = :exit_price,
                    pnl = :pnl,
                    closed_at = :closed_at,
                    outcome = CAST(:outcome AS jsonb),
                    market_regime = :market_regime
                WHERE id = :id AND status = 'open'
            """),
            {
                "id": decision_id,
                "exit_price": exit_price,
                "pnl": pnl,
                "closed_at": closed_at,
                "outcome": json.dumps(outcome, default=str) if outcome else None,
                "market_regime": market_regime if market_regime and market_regime != "unknown" else None,
            },
        )
        applied = result.rowcount > 0

        self.session.commit()

        if not applied:
            return False

        from database.repositories.event_log_repository import EventLogRepository

        EventLogRepository(self.session).record(
            event_type="position_closed",
            entity_type="decision",
            entity_id=UUID(str(decision_id)),
            payload={"exit_price": exit_price, "pnl": pnl},
        )
        return True

    def close_position_partial(
        self,
        decision_id: str,
        close_qty: float,
        exit_price: float,
        pnl: float,
        fee: float,
        exit_reason: str,
        closed_at,
    ) -> dict:
        """Faz 268 — kullanıcı isteği: "pozisyonun yarısını/çeyreğini kademeli
        kapatabilen mekanizma." Var olan close_position() her zaman TÜM
        pozisyonu kapatıyordu (tek satır, tek işlem = binary open/closed).
        Burada satır 'open' kalıyor, sadece quantity gerçekten kapatılan
        miktar kadar azaltılıyor — RiskEngine/risk_state.py zaten quantity'yi
        her cycle'da taze okuyor, yani capital_used_pct otomatik ve doğru
        küçülüyor, hiçbir risk-motoru değişikliği gerekmiyor. Realize edilen
        pnl bir sonraki (kısmi ya da nihai) kapanışta kaybolmasın diye
        outcome jsonb'sinde (zaten agent_contributions gibi yapılı veri için
        kullanılan aynı kolon) partial_closes listesi + kümülatif
        realized_pnl olarak biriktiriliyor; nihai tam kapanışta bu kümülatif
        pnl'e son dilimin pnl'i eklenerek decisions.pnl yazılıyor — closed_
        trades_summary()'nin sum(pnl)'i hiçbir şema değişikliği olmadan
        doğru kalıyor."""
        row = self.get_by_id(decision_id)
        if row is None or row.get("status") != "open":
            raise ValueError(f"decision {decision_id} not open")

        current_qty = float(row.get("quantity") or 0.0)
        new_qty = current_qty - close_qty
        existing_outcome = row.get("outcome") or {}
        realized_pnl = float(existing_outcome.get("realized_pnl") or 0.0) + pnl
        partial_closes = list(existing_outcome.get("partial_closes") or [])
        partial_closes.append({
            "close_qty": close_qty,
            "exit_price": exit_price,
            "pnl": pnl,
            "fee": fee,
            "exit_reason": exit_reason,
            "closed_at": str(closed_at),
        })
        outcome = {**existing_outcome, "realized_pnl": realized_pnl, "partial_closes": partial_closes}

        self.session.execute(
            text("""
                UPDATE decisions
                SET quantity = :new_qty, outcome = CAST(:outcome AS jsonb)
                WHERE id = :id AND status = 'open'
            """),
            {"id": decision_id, "new_qty": new_qty, "outcome": json.dumps(outcome, default=str)},
        )
        self.session.commit()

        return {"remaining_quantity": new_qty, "realized_pnl": realized_pnl}

    def update_stop_loss_price(self, decision_id: str, new_stop_loss_price: float) -> None:
        """Faz 268ae — kullanıcı isteği: "pozisyon kârlı gidiyor ama tersine
        döndü, stop yükseltilse tam zarar yerine nötr/az zararla çıkabilir."
        Açık bir pozisyonun stop_loss_price'ını sonradan güncellemek için —
        önceden decisions.stop_loss_price sadece açılışta bir kez yazılıyor,
        hiçbir kod onu sonradan değiştirmiyordu (bkz. PositionCloser.
        _apply_breakeven_stop)."""
        self.session.execute(
            text("UPDATE decisions SET stop_loss_price = :stop WHERE id = :id AND status = 'open'"),
            {"id": decision_id, "stop": new_stop_loss_price},
        )
        self.session.commit()

    def update_exchange_stop_order_id(self, decision_id: str, new_exchange_stop_order_id: str) -> None:
        """Faz 315 — Execution Layer, Faz 1. testnet modundaki bir
        pozisyonda breakeven/trailing ratchet tetiklendiğinde, borsadaki
        eski STOP_MARKET emri iptal edilip yenisi konuyor (bkz. services/
        execution_service.py::ExecutionService.update_stop_price) —
        update_stop_loss_price ile AYNI zamanda, ama AYRI bir çağrı:
        biri (bu) borsadaki GERÇEK emir kimliğini, diğeri dashboard'un
        okuduğu fiyatı günceller."""
        self.session.execute(
            text(
                "UPDATE decisions SET exchange_stop_order_id = :order_id "
                "WHERE id = :id AND status = 'open'"
            ),
            {"id": decision_id, "order_id": new_exchange_stop_order_id},
        )
        self.session.commit()

    def update_exchange_sync_status(self, decision_id: str, status: str) -> None:
        """Faz 315 — services/execution_reconciliation.py'nin, DB'deki bir
        testnet pozisyonu ile borsadaki gerçek durumu karşılaştırdıktan
        SONRA yazdığı tek alan. Sadece işaretler/loglar — hiçbir zaman
        pozisyonun kendisini (stop/entry/pnl) burada OTOMATİK
        düzeltmiyoruz (bkz. plan: "asla veri uydurma")."""
        self.session.execute(
            text("UPDATE decisions SET exchange_sync_status = :status WHERE id = :id"),
            {"id": decision_id, "status": status},
        )
        self.session.commit()

    def update_outcome(
        self,
        decision_id: str,
        pnl: float,
        status: str,
        outcome: dict | None = None,
    ) -> None:
        self.session.execute(
            text("""
                UPDATE decisions
                SET
                    pnl = :pnl,
                    status = :status,
                    outcome = CAST(:outcome AS jsonb)
                WHERE id = :id
            """),
            {
                "id": decision_id,
                "pnl": pnl,
                "status": status,
                "outcome": json.dumps(outcome, default=str) if outcome else None,
            },
        )

        self.session.commit()
