"""Faz 215: kullanıcı isteği — "dün ne kadar ROI yapmış, haftalık/aylık/
yıllık ne olmuş" dashboard'da hiç görünmüyordu. /api/v1/performance
gerçek kapanmış işlemlerden (decisions tablosu) günlük/haftalık/aylık/
yıllık PnL + ROI + win rate hesaplıyor."""
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from contracts.auth import Role
from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def _closed_trade(pnl: float, symbol: str, direction: str = "LONG"):
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), symbol=symbol, proposed_direction=direction, final_action=direction,
        final_size=1.0, confidence=0.6,
        status="open", entry_price=100.0, quantity=1.0, opened_at=now,
    )
    with SessionFactory.get_session() as session:
        repo = DecisionPersistor(session)
        repo.persist(event)
        repo.close_position(decision_id=str(event.id), exit_price=100.0, pnl=pnl, closed_at=now)
    return event.id


def test_performance_endpoint_reflects_real_closed_trades():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"PERF{uuid4().hex[:8]}"
        _closed_trade(pnl=50.0, symbol=symbol)
        _closed_trade(pnl=-20.0, symbol=symbol)

        client = _client()
        response = client.get("/api/v1/performance", headers=make_authed_headers(Role.VIEWER))
        assert response.status_code == 200
        body = response.json()

        assert body["all_time"]["trade_count"] >= 2
        assert "daily" in body and "weekly" in body and "monthly" in body and "yearly" in body
        assert body["daily"][0]["trade_count"] >= 2
        assert 0.0 <= body["daily"][0]["win_rate"] <= 1.0
        assert body["starting_capital"] > 0


def test_performance_endpoint_includes_win_rate_by_direction():
    """Faz 322 — kullanıcı isteği: "genel toplamda long/short kazanma
    oranı" kartı. Paylaşımlı test DB'si zaten kirli olduğundan (bkz.
    project_shared_test_state_bloat) kesin sayı değil, ŞEKİL/tutarlılık
    doğrulanıyor: her iki yön de mevcut, sayılar birbirini tutuyor."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        long_symbol = f"PERFLONG{uuid4().hex[:8]}"
        short_symbol = f"PERFSHORT{uuid4().hex[:8]}"
        _closed_trade(pnl=50.0, symbol=long_symbol, direction="LONG")
        _closed_trade(pnl=-20.0, symbol=short_symbol, direction="SHORT")
        _closed_trade(pnl=-5.0, symbol=short_symbol, direction="SHORT")

        client = _client()
        response = client.get("/api/v1/performance", headers=make_authed_headers(Role.VIEWER))
        body = response.json()

        by_direction = body["by_direction"]
        assert set(by_direction.keys()) == {"LONG", "SHORT"}
        for direction in ("LONG", "SHORT"):
            stats = by_direction[direction]
            assert stats["trade_count"] == stats["win_count"] + stats["loss_count"]
            assert 0.0 <= stats["win_rate"] <= 1.0
        assert by_direction["LONG"]["win_count"] >= 1
        assert by_direction["SHORT"]["loss_count"] >= 2


def test_closed_trades_summary_by_direction_counts_wins_and_losses_separately():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"PERFDIR{uuid4().hex[:8]}"
        _closed_trade(pnl=10.0, symbol=symbol, direction="LONG")
        _closed_trade(pnl=-10.0, symbol=symbol, direction="LONG")
        _closed_trade(pnl=10.0, symbol=symbol, direction="SHORT")

        with SessionFactory.get_session() as session:
            result = DecisionPersistor(session).closed_trades_summary_by_direction()

        assert result["LONG"]["trade_count"] >= 2
        assert result["LONG"]["win_count"] >= 1
        assert result["LONG"]["loss_count"] >= 1
        assert result["SHORT"]["trade_count"] >= 1
        assert result["SHORT"]["win_count"] >= 1


def test_trades_endpoint_summary_matches_performance_all_time_even_when_table_is_capped():
    """Faz 224: kritik bulgu — kullanıcı: "sürekli işlem alıyor kapatıyor
    ama kapanmış işlem sayısı 100 görünüyor, bir ara 400 küsürdü, bu
    dashboarda güvenemiyorum." Kök neden: GET /trades'in summary'si
    list_closed_trades(limit=...)'ın DÖNDÜRDÜĞÜ (varsayılan 100) dilimden
    hesaplanıyordu, GET /performance ise ayrı (limit=10000) bir hesap
    yapıyordu — aynı isimli iki sayı iki farklı gerçek kümeden geliyordu.
    Bu test, /trades'e KÜÇÜK bir tablo limiti verilse bile (ör. limit=1,
    tabloda tek satır dönse bile) summary.count'un GERÇEK toplamı
    yansıttığını, ve bunun /performance.all_time ile birebir aynı
    olduğunu doğruluyor."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"TRADESYNC{uuid4().hex[:8]}"
        _closed_trade(pnl=50.0, symbol=symbol)
        _closed_trade(pnl=-20.0, symbol=symbol)
        _closed_trade(pnl=30.0, symbol=symbol)

        client = _client()
        trades_resp = client.get(
            "/api/v1/trades", params={"limit": 1}, headers=make_authed_headers(Role.VIEWER)
        )
        perf_resp = client.get("/api/v1/performance", headers=make_authed_headers(Role.VIEWER))

        assert trades_resp.status_code == 200 and perf_resp.status_code == 200
        trades_body = trades_resp.json()
        perf_body = perf_resp.json()

        # Tablo satırı gerçekten limitli (1) ama summary limitten bağımsız.
        assert len(trades_body["trades"]) == 1
        assert trades_body["summary"]["count"] == perf_body["all_time"]["trade_count"]
        assert trades_body["summary"]["total_pnl"] == perf_body["all_time"]["total_pnl"]
        assert trades_body["summary"]["win_rate"] == perf_body["all_time"]["win_rate"]
        assert trades_body["summary"]["count"] >= 3


def test_performance_endpoint_breaks_down_win_rate_and_pnl_by_trade_type():
    """Faz 268f — kullanıcı isteği: "kısa/orta/uzun/swing/scalp gibi işlem
    tiplerinden hangileri başarılı olmuş, dashboard'a otomatik yansısın."
    Transactions.tsx::tradeTypeBadge() ile AYNI sınıflandırma (stop
    mesafesi %4.5/%9 eşikleri) burada da uygulanıp /performance'a
    by_trade_type olarak ekleniyor mu?

    Faz 323 — kullanıcı bulgusu: "orta_vadeli" (timeframe IN ('4h','1d'))
    kategorisi tamamen kaldırıldı — candle_timeframe gibi ilgisiz bir
    ayara bağımlı, kırılgan bir vekildi (6 gün boyunca scalp/swing'i hiç
    yeni kayıt almadan dondurmuştu). Bu test artık timeframe='4h' bir
    işlemin GERÇEK stop mesafesine göre (silinmeden) doğru sınıflandığını
    kanıtlıyor — eskiden bu senaryo yanlışlıkla "orta_vadeli"ye
    düşüyordu, artık stop mesafesi %2 < %4.5 olduğu için scalp'e giriyor."""
    from contracts.decision_event import DecisionEvent

    now = datetime.now(UTC)

    def _closed_with(symbol, pnl, entry_price=100.0, stop_loss_price=None, timeframe=None):
        event = DecisionEvent(
            id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
            final_size=1.0, confidence=0.6, status="open",
            entry_price=entry_price, quantity=1.0, opened_at=now,
            stop_loss_price=stop_loss_price, timeframe=timeframe,
        )
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            repo.persist(event)
            repo.close_position(decision_id=str(event.id), exit_price=entry_price, pnl=pnl, closed_at=now)

    scalp_symbol = f"TTSCALP{uuid4().hex[:6]}"
    swing_4h_symbol = f"TTSWING4H{uuid4().hex[:6]}"

    # Scalp: |entry-stop|/entry = %2 < %4.5 eşiği. İki işlem, biri kazanç
    # biri kayıp -> win_rate tam %50, hesabı elle doğrulanabilir.
    _closed_with(scalp_symbol, pnl=10.0, entry_price=100.0, stop_loss_price=98.0)
    _closed_with(scalp_symbol, pnl=-5.0, entry_price=100.0, stop_loss_price=98.0)
    # timeframe='4h' ama stop mesafesi %10 (>= %4.5) -> artık swing'e
    # girmeli, "orta_vadeli" diye ayrı bir kovaya değil.
    _closed_with(swing_4h_symbol, pnl=20.0, entry_price=100.0, stop_loss_price=90.0, timeframe="4h")

    client = _client()
    response = client.get("/api/v1/performance", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    by_type = response.json()["by_trade_type"]

    assert "orta_vadeli" not in by_type
    assert by_type["scalp"]["trade_count"] >= 2
    assert by_type["swing"]["trade_count"] >= 1
    # Faz 400-devam — canonical evaluation cohort görünürlüğü: by_trade_type
    # ayrı bir list_closed_trades(limit=100_000) çağrısından geliyor,
    # all_time'ın limitsiz closed_trades_summary'sinden DEĞİL.
    window = response.json()["by_trade_type_evaluation_window"]
    assert window["limit"] == 100_000
    assert window["exclude_experiment_buckets"] == ["pump_fade_v1"]


def test_deployed_notional_reflects_real_margin_not_leveraged_notional():
    """Faz 268ah — kullanıcı bulgusu: "ROI konusunda problem olduğundan
    şüpheliyim, pozisyon büyüklükleri ilişkisi kaotik." Gerçek bug:
    DecisionRecorder kaldıraçlı pozisyonlarda quantity'yi zaten leverage
    ile çarpıyordu (Faz 255) — entry_price*quantity GERÇEK yatırılan
    marjin değil, kaldıraçlı TAM notional'dı. Kapanmış işlemlerde
    doğrulandı: $419k "deployed" gösteriyordu, gerçek marjin $33.8k
    (12.4x fark) — sembol başına farklı kaldıraç notional'ı orantısız
    şişiriyordu. Bu test: 10x kaldıraçlı bir pozisyonun deployed_notional'a
    katkısının notional (entry*quantity) değil, gerçek marjin (notional/
    leverage) olduğunu doğruluyor."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"PERFLEV{uuid4().hex[:8]}"
        now = datetime.now(UTC)
        # 10x kaldıraç, entry=100, quantity=10 (zaten leverage ile
        # çarpılmış gerçek değer) -> notional=$1000, gerçek marjin=$100.
        event = DecisionEvent(
            id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
            final_size=10.0, confidence=0.6,
            status="open", entry_price=100.0, quantity=10.0, opened_at=now,
            leverage=10.0,
        )
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            repo.persist(event)
            before = repo.closed_trades_summary()["deployed_notional"]
            repo.close_position(decision_id=str(event.id), exit_price=100.0, pnl=5.0, closed_at=now)
            after = repo.closed_trades_summary()["deployed_notional"]

        added = after - before
        assert abs(added - 100.0) < 0.01  # gerçek marjin ($100), notional ($1000) DEĞİL


def test_trades_marked_excluded_from_stats_do_not_pollute_aggregates():
    """Faz 238: kullanıcı isteği — "kirli geçmiş veriyi temizle." Kendi
    aşırı-capital deneyleri sırasında (starting_capital 10-500 milyar)
    decisions tablosunda ölçek dışı bir dönem birikmişti (gerçek notional
    ~$1333 hedefken bazı işlemler $58 milyon'a ulaşmıştı). Satırlar
    SİLİNMİYOR (excluded_from_stats=true ile işaretleniyor, faz238
    migration) — bu test, işaretli bir satırın hem /trades hem
    /performance agregatlarından GERÇEKTEN dışlandığını doğruluyor."""
    import sqlalchemy

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        client = _client()
        # Paylaşılan test DB'de önceki testlerden kalan durum olabilir —
        # mutlak bir toplam yerine, kendi eklediğimiz kirli satırın
        # agregata GERÇEKTEN girip girmediğini önce/sonra farkıyla ölçüyoruz.
        before_total = client.get(
            "/api/v1/performance", headers=make_authed_headers(Role.VIEWER)
        ).json()["all_time"]["total_pnl"]

        symbol = f"DIRTY{uuid4().hex[:8]}"
        sane_id = _closed_trade(pnl=10.0, symbol=symbol)

        now = datetime.now(UTC)
        dirty_event = DecisionEvent(
            id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
            final_size=1.0, confidence=0.6,
            status="open", entry_price=1_000_000.0, quantity=100.0, opened_at=now,
        )
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            repo.persist(dirty_event)
            repo.close_position(
                decision_id=str(dirty_event.id), exit_price=1_000_000.0, pnl=99_999_999.0, closed_at=now,
            )
            session.execute(
                sqlalchemy.text("UPDATE decisions SET excluded_from_stats = true WHERE id = :id"),
                {"id": str(dirty_event.id)},
            )
            session.commit()

        trades_resp = client.get(
            "/api/v1/trades", params={"limit": 10000}, headers=make_authed_headers(Role.VIEWER)
        )
        perf_resp = client.get("/api/v1/performance", headers=make_authed_headers(Role.VIEWER))
        body = trades_resp.json()
        perf_body = perf_resp.json()

        returned_ids = {t["id"] for t in body["trades"]}
        assert str(dirty_event.id) not in returned_ids
        assert str(sane_id) in returned_ids
        # Toplam pnl'deki gerçek değişim, sadece sane işlemin (+10) kadar
        # olmalı — kirli işlemin +99,999,999'u agregata hiç girmemiş.
        after_total = perf_body["all_time"]["total_pnl"]
        assert abs((after_total - before_total) - 10.0) < 0.01


def test_trades_and_performance_summaries_count_tp_and_sl_closes():
    """Dashboard'a eklenen TP/SL sayaçları — outcome jsonb'sindeki
    exit_reason'a göre gerçek sayım, /trades ve /performance'ta AYNI
    closed_trades_summary()'den geldiği için birebir eşleşmeli."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"TPSL{uuid4().hex[:8]}"
        now = datetime.now(UTC)

        def _closed_with_reason(pnl: float, exit_reason: str):
            event = DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                final_size=1.0, confidence=0.6, status="open",
                entry_price=100.0, quantity=1.0, opened_at=now,
            )
            with SessionFactory.get_session() as session:
                repo = DecisionPersistor(session)
                repo.persist(event)
                repo.close_position(
                    decision_id=str(event.id), exit_price=100.0, pnl=pnl, closed_at=now,
                    outcome={"exit_reason": exit_reason},
                )

        _closed_with_reason(10.0, "take_profit")
        _closed_with_reason(10.0, "take_profit")
        _closed_with_reason(-5.0, "stop_loss")

        client = _client()
        trades_body = client.get(
            "/api/v1/trades", params={"limit": 10000}, headers=make_authed_headers(Role.VIEWER)
        ).json()
        perf_body = client.get("/api/v1/performance", headers=make_authed_headers(Role.VIEWER)).json()

        assert trades_body["summary"]["tp_count"] == perf_body["all_time"]["tp_count"]
        assert trades_body["summary"]["sl_count"] == perf_body["all_time"]["sl_count"]
        assert trades_body["summary"]["tp_count"] >= 2
        assert trades_body["summary"]["sl_count"] >= 1


def test_manual_closes_are_counted_as_tp_or_sl_by_real_outcome_not_a_separate_bucket():
    """Faz 268-sonrası — kullanıcı isteği: manuel kapatılan (exit_reason=
    'manual_full') işlemler ayrı bir 'manuel' kovasında değil, GERÇEK
    sonuçlarına göre (kârlıysa TP gibi, zarardaysa SL gibi) sayılmalı —
    kapanış mekanizması değil, gerçek kâr/zarar önemli."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        now = datetime.now(UTC)

        def _open_and_manually_close(pnl: float) -> None:
            symbol = f"MANUALCLOSE{uuid4().hex[:8]}"
            event = DecisionEvent(
                id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
                final_size=1.0, confidence=0.6, status="open",
                entry_price=100.0, quantity=1.0, opened_at=now,
            )
            with SessionFactory.get_session() as session:
                repo = DecisionPersistor(session)
                repo.persist(event)
                repo.close_position(
                    decision_id=str(event.id), exit_price=100.0 + pnl, pnl=pnl, closed_at=now,
                    outcome={"exit_reason": "manual_full"},
                )

        client = _client()
        before = client.get("/api/v1/performance", headers=make_authed_headers(Role.VIEWER)).json()["all_time"]

        _open_and_manually_close(pnl=1.0)   # kârlı manuel kapanış -> TP gibi sayılmalı
        _open_and_manually_close(pnl=-1.0)  # zararlı manuel kapanış -> SL gibi sayılmalı

        trades_body = client.get(
            "/api/v1/trades", params={"limit": 10000}, headers=make_authed_headers(Role.VIEWER)
        ).json()
        perf_body = client.get("/api/v1/performance", headers=make_authed_headers(Role.VIEWER)).json()

        assert trades_body["summary"]["tp_count"] == perf_body["all_time"]["tp_count"]
        assert trades_body["summary"]["sl_count"] == perf_body["all_time"]["sl_count"]
        assert perf_body["all_time"]["tp_count"] == before["tp_count"] + 1
        assert perf_body["all_time"]["sl_count"] == before["sl_count"] + 1

        # Faz 311 — kullanıcı isteği (uzun süredir bekleyen todo): "toplam
        # manuel kapanan işlem" kartı — manual_full_count her iki manuel
        # kapanışı da (kârlı VE zararlı) sayar, tp_count/sl_count'a
        # bölünmesinden BAĞIMSIZ ayrı bir bilgilendirme alanı.
        assert trades_body["summary"]["manual_full_count"] == perf_body["all_time"]["manual_full_count"]
        assert perf_body["all_time"]["manual_full_count"] == before["manual_full_count"] + 2
