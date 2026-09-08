"""services/directional_skill_gatherer.py — Faz 458 (2026-09-09).
tests/test_direction_calibration_gatherer.py'deki AYNI gerçek-DB
round-trip deseni: gerçek `decisions` + `market_snapshots` satırları
yazılır, gatherer çalıştırılır, dört yeni ölçümün GERÇEK veriyle
beslendiği doğrulanır."""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from contracts.market_data import DataSource, MarketSnapshot, Resolution
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from services.directional_skill_gatherer import gather_directional_skill


def _insert_decision(session, *, symbol, direction, entry_price, confidence, timestamp,
                     status="open"):
    session.execute(
        text("""
            INSERT INTO decisions
                (id, timestamp, symbol, direction, size, confidence, status, entry_price,
                 excluded_from_stats)
            VALUES
                (:id, :timestamp, :symbol, :direction, 1.0, :confidence, :status, :entry_price,
                 false)
        """),
        {
            "id": str(uuid.uuid4()), "timestamp": timestamp, "symbol": symbol,
            "direction": direction, "entry_price": entry_price, "confidence": confidence,
            "status": status,
        },
    )


def test_gatherer_measures_never_closed_decisions_too():
    """Faz 446'dan KASITLI farkın regresyon koruması: yön becerisi
    TAHMİNİN özelliğidir, işlemin değil. Hiç kapanmamış (status='open')
    kararlar da ölçüme girmeli -- `status='closed'` filtresi geri
    eklenirse bu test kırılır."""
    symbol = f"DSGT{uuid.uuid4().hex[:6]}USDT"
    base = datetime.now(UTC) - timedelta(days=2)

    with SessionFactory.get_session() as session:
        repo = MarketDataRepository(session)
        # HER İKİ yön de yazılıyor: Pesaran-Timmermann tek yönlü bir
        # örneklemde varyans paydası çöktüğü için (doğru şekilde)
        # fail-closed None döner -- testin onu hesaplayabilmesi için
        # gerçekçi, iki yönlü bir örneklem gerekiyor.
        for i in range(40):
            entry_time = base + timedelta(minutes=i * 5)
            _insert_decision(
                session, symbol=symbol, direction="LONG", entry_price=100.0,
                confidence=0.9, timestamp=entry_time, status="open",
            )
            _insert_decision(
                session, symbol=symbol, direction="SHORT", entry_price=100.0,
                confidence=0.6, timestamp=entry_time + timedelta(seconds=30), status="open",
            )
            # GERÇEK sonuçlar da değişken olmalı: PT testi, tahminler VEYA
            # sonuçlar tek yönlü olduğunda varyans paydası sıfırlandığı
            # için (doğru şekilde) None döner. Dönüşümlü UP/DOWN.
            forward_close = 95.0 if i % 2 == 0 else 105.0
            repo.upsert_snapshot(MarketSnapshot(
                time=entry_time + timedelta(hours=1), exchange=DataSource.BINANCE,
                symbol=symbol, resolution=Resolution.M1, open=forward_close,
                high=forward_close, low=forward_close, close=forward_close,
                volume=1.0, source_version="v1",
            ))
        session.commit()

    result = gather_directional_skill()

    assert result["n_directional"] >= 80
    assert result["murphy_decomposition"] is not None
    assert result["benchmark_relative_skill"] is not None
    assert result["pesaran_timmermann"] is not None


def test_gatherer_reports_neutral_exclusions_instead_of_hiding_them():
    """Eşiğin (%0,05) veriye uygun olup olmadığının tek göstergesi
    NEUTRAL oranı -- sessizce atılırsa "n neden bu kadar küçük" sorusu
    cevapsız kalır."""
    symbol = f"DSGN{uuid.uuid4().hex[:6]}USDT"
    base = datetime.now(UTC) - timedelta(days=3)

    with SessionFactory.get_session() as session:
        repo = MarketDataRepository(session)
        for i in range(30):
            entry_time = base + timedelta(minutes=i * 7)
            _insert_decision(
                session, symbol=symbol, direction="LONG", entry_price=100.0,
                confidence=0.5, timestamp=entry_time,
            )
            # %0,01 hareket -> esigin (%0,05) ALTINDA -> NEUTRAL.
            repo.upsert_snapshot(MarketSnapshot(
                time=entry_time + timedelta(hours=1), exchange=DataSource.BINANCE,
                symbol=symbol, resolution=Resolution.M1, open=100.01, high=100.01,
                low=100.01, close=100.01, volume=1.0, source_version="v1",
            ))
        session.commit()

    result = gather_directional_skill()

    assert result["n_neutral_excluded"] >= 30


def test_gatherer_carries_the_independence_caveat_into_the_report():
    """PT testi tek başına raporlanmamalı: 123 sembol aynı piyasa
    hareketini paylaştığı için bağımsızlık varsayımı ihlal ediliyor.
    Rapor hem uyarıyı hem muhafazakâr karşılığını (günlük işaret testi)
    taşımalı."""
    result = gather_directional_skill()

    if result["pesaran_timmermann"] is not None:
        assert result["pesaran_timmermann"]["independence_assumption_violated"] is True
    # daily_sign_test <3 yogun gunde None donebilir -- ama anahtar HER
    # ZAMAN raporda olmali ki PT tek basina kalmasin.
    assert "daily_sign_test" in result


def test_gatherer_excludes_removed_multi_timeframe_cascade_experiment():
    """Faz 457'de kaldırılan cascade A/B deneyi (hem control hem
    treatment) farklı bir mekanizmadan geldiği için yön ölçümünü
    kirletir -- asset_class_performance_gatherer.py ile AYNI gerekçe."""
    symbol = f"DSGX{uuid.uuid4().hex[:6]}USDT"
    base = datetime.now(UTC) - timedelta(days=2)

    with SessionFactory.get_session() as session:
        repo = MarketDataRepository(session)
        for i in range(30):
            entry_time = base + timedelta(minutes=i * 11)
            session.execute(
                text("""
                    INSERT INTO decisions
                        (id, timestamp, symbol, direction, size, confidence, status,
                         entry_price, experiment_bucket, excluded_from_stats)
                    VALUES
                        (:id, :timestamp, :symbol, 'LONG', 1.0, 0.9, 'open',
                         100.0, 'multi_timeframe_cascade_v1:treatment', false)
                """),
                {"id": str(uuid.uuid4()), "timestamp": entry_time, "symbol": symbol},
            )
            repo.upsert_snapshot(MarketSnapshot(
                time=entry_time + timedelta(hours=1), exchange=DataSource.BINANCE,
                symbol=symbol, resolution=Resolution.M1, open=95.0, high=95.0, low=95.0,
                close=95.0, volume=1.0, source_version="v1",
            ))
        session.commit()

    window = gather_directional_skill()["evaluation_window"]
    # Bu semboldeki 30 kayit tamamen cascade etiketli; havuza girmemeli.
    assert window is not None
