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
                    take_profit_price,
                    leverage,
                    liquidation_price,
                    timeframe
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
                    :take_profit_price,
                    :leverage,
                    :liquidation_price,
                    :timeframe
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
            },
        )

        self.session.commit()

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

    def list_open_positions(self, limit: int = 200):
        rows = self.session.execute(
            text(
                "SELECT * FROM decisions WHERE status = 'open' "
                "ORDER BY opened_at DESC LIMIT :limit"
            ),
            {"limit": limit},
        ).mappings().all()

        return [dict(r) for r in rows]

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

    def list_closed_trades(self, limit: int = 200):
        # Faz 238: kullanıcı isteği — "kirli geçmiş veriyi temizle."
        # excluded_from_stats=true işaretli satırlar (aşırı capital
        # testlerinden kalan, gerçek olmayan notional'lı işlemler)
        # varsayılan olarak dışarıda bırakılıyor — silinmiyor, sadece
        # normal görünümden hariç tutuluyor.
        rows = self.session.execute(
            text(
                "SELECT * FROM decisions WHERE status = 'closed' AND excluded_from_stats = false "
                "ORDER BY closed_at DESC LIMIT :limit"
            ),
            {"limit": limit},
        ).mappings().all()

        return [dict(r) for r in rows]

    def closed_trades_summary(self) -> dict:
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
        AYNI, gerçek toplamı kullanabilir."""
        # Faz 238: excluded_from_stats=true işaretli (kirli/aşırı-test)
        # satırlar agregata hiç girmiyor.
        row = self.session.execute(
            text(
                "SELECT count(*) AS trade_count, "
                "sum(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins, "
                "sum(pnl) AS total_pnl, "
                "sum(entry_price * quantity) AS deployed_notional "
                "FROM decisions WHERE status = 'closed' AND excluded_from_stats = false"
            )
        ).mappings().one()
        excluded_count = self.session.execute(
            text("SELECT count(*) FROM decisions WHERE status = 'closed' AND excluded_from_stats = true")
        ).scalar()
        trade_count = row["trade_count"] or 0
        return {
            "trade_count": trade_count,
            "win_rate": (row["wins"] / trade_count) if trade_count else 0.0,
            "total_pnl": float(row["total_pnl"] or 0.0),
            "deployed_notional": float(row["deployed_notional"] or 0.0),
            "excluded_count": excluded_count or 0,
        }

    def performance_by_period(self, period: str, limit: int = 200) -> list[dict]:
        """Faz 215: kullanıcı isteği — "dün ne kadar ROI yapmış, haftalık/
        aylık/yıllık ne olmuş" dashboard'da hiç görünmüyordu. period:
        Postgres date_trunc'ın kabul ettiği bir değer (day/week/month/year).
        Her kova için gerçek kapanmış işlemlerden pnl toplamı/işlem
        sayısı/win rate — icat edilmiş bir sayı değil."""
        if period not in ("day", "week", "month", "year"):
            raise ValueError(f"invalid period: {period}")

        rows = self.session.execute(
            text(f"""
                SELECT
                    date_trunc('{period}', closed_at) AS bucket,
                    count(*) AS trade_count,
                    sum(pnl) AS total_pnl,
                    sum(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
                    sum(entry_price * quantity) AS deployed_notional
                FROM decisions
                WHERE status = 'closed' AND closed_at IS NOT NULL AND excluded_from_stats = false
                GROUP BY bucket
                ORDER BY bucket DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).mappings().all()

        return [dict(r) for r in rows]

    def close_position(
        self,
        decision_id: str,
        exit_price: float,
        pnl: float,
        closed_at,
        outcome: dict | None = None,
    ) -> None:
        self.session.execute(
            text("""
                UPDATE decisions
                SET
                    status = 'closed',
                    exit_price = :exit_price,
                    pnl = :pnl,
                    closed_at = :closed_at,
                    outcome = CAST(:outcome AS jsonb)
                WHERE id = :id
            """),
            {
                "id": decision_id,
                "exit_price": exit_price,
                "pnl": pnl,
                "closed_at": closed_at,
                "outcome": json.dumps(outcome, default=str) if outcome else None,
            },
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
