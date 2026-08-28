"""Faz 368 — GPT dış rapor önerisi (kullanıcı isteği: "derin doğrulama
testleri"): "golden trade ledger" / cross-module tutarlılık kontrolü.
Endişe: farklı analitik modüller AYNI decisions tablosundan kendi ayrı
SQL sorgularını çekiyor (tekil bir decision_id lineage/materialized view
YOK) — "win" bazı modüllerde outcome->>'win' JSON alanından, bazılarında
doğrudan pnl>0'dan geliyor; bunlar SESSİZCE birbirinden sapabilirdi.

GERÇEK prod veritabanına (quantdb, 3502 gerçek kapanmış karar) karşı BİR
KEZ elle doğrulandı (2026-08-28, read-only): 0 uyuşmazlık — pnl işareti
ile outcome.win alanı her yerde birebir eşleşiyor, direction her zaman
LONG/SHORT.

Bu invaryantı KALICI bir pytest testi olarak (tüm decisions tablosunu
tarayarak) tutmayı denedim ama BİLEREK vazgeçtim: quantdb_test paylaşımlı
— tests/test_calibration_api.py gibi bazı testler, ECE/kalibrasyon
matematiğini test etmek için KASITLI olarak pnl'den bağımsız bir
outcome.win değeri yazıyor (sabit dummy pnl=1.0 + i<12 gibi bir kalıpla
%80 'gerçek' kalibrasyon simüle ediyor) — bu GERÇEK bir tutarsızlık
DEĞİL, o testin kendi meşru senaryosu. Tüm tabloyu tarayan bir test bu
tür meşru senaryolarla sürekli çakışırdı (yanlış pozitif). Bunun yerine
aşağıdaki test SADECE kendi izole ürettiği veriyi kontrol ediyor —
paylaşılan tabloyu asla taramıyor, bu yüzden başka hiçbir testin meşru
senaryosuyla asla çakışmaz."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory


def _persist_closed_trade(symbol: str, direction: str, pnl: float, closed_at: datetime) -> None:
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        event = DecisionEvent(
            id=uuid4(), symbol=symbol, proposed_direction=direction, final_action=direction,
            final_size=0.1, confidence=0.7, status="open", entry_price=100.0, quantity=1.0,
            opened_at=closed_at - timedelta(minutes=10), agent_opinions=[],
            market_snapshot={"features": {}},
        )
        persistor.persist(event)
        persistor.close_position(
            decision_id=str(event.id), exit_price=101.0, pnl=pnl, closed_at=closed_at,
            outcome={"win": pnl > 0},
        )


def test_symbol_direction_performance_gatherer_matches_an_independent_raw_recomputation():
    """Gerçek (sentetik ama gerçek DB satırları olarak yazılmış) kapanmış
    işlemler üretip, services/symbol_direction_performance_gatherer.py'nin
    (bugün eklendi) çıktısını AYNI filtreleri BAĞIMSIZ olarak yeniden
    yazılmış ham bir SQL sorgusuyla çapraz doğrular — gatherer'ın kendi
    mantığını tekrar test etmiyoruz (bu zaten tests/test_symbol_
    direction_performance_gatherer.py'de var), modülün DB'den okuduğu
    sayıların bağımsız bir yeniden hesaplamayla eştiğini doğruluyoruz.
    win/pnl tutarlılığı da BURADA, kendi izole verimiz üzerinde
    doğrulanıyor (paylaşılan tabloyu taramadan)."""
    from services.symbol_direction_performance_gatherer import gather_symbol_direction_performance

    base_time = datetime.now(UTC) + timedelta(days=3656)
    symbol = f"LEDGER{uuid4().hex[:8]}USDT"

    try:
        for i in range(7):
            pnl = 50.0 if i < 4 else -30.0  # 4 kazandı, 3 kaybetti
            _persist_closed_trade(symbol, "LONG", pnl, closed_at=base_time - timedelta(hours=i))

        result = gather_symbol_direction_performance()
        key = f"{symbol}_LONG"
        assert key in result["by_symbol_direction"]
        entry = result["by_symbol_direction"][key]

        with SessionFactory.get_session() as session:
            row = session.execute(text(
                "SELECT COUNT(*) n, SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) wins, SUM(pnl) total_pnl, "
                "SUM(CASE WHEN (pnl > 0) != (outcome->>'win' = 'true') THEN 1 ELSE 0 END) win_pnl_mismatches "
                "FROM decisions WHERE status = 'closed' AND excluded_from_stats = false "
                "AND symbol = :symbol AND direction = 'LONG'"
            ), {"symbol": symbol}).mappings().first()

        assert row["win_pnl_mismatches"] == 0
        assert row["n"] == entry["sample_size"]
        assert round(row["wins"] / row["n"], 4) == entry["win_rate"]
        assert abs(round(float(row["total_pnl"]), 2) - entry["total_pnl"]) < 0.01
    finally:
        with SessionFactory.get_session() as session:
            session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
            session.commit()
