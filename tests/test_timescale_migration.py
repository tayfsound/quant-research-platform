"""Faz 161: TimescaleDB hypertable migration verify.

Faz 182: this used to xfail locally — create_hypertable() failed on a
non-empty DB, and separately (a deeper issue found while root-causing that)
Timescale requires the partitioning column in the primary key, which these
tables didn't have. Both fixed: faz161's migration now widens the PK to
(id, timestamp) and passes migrate_data=>true; verified against both a
fresh scratch DB and the real local dev DB (4996 existing decisions rows,
zero data loss). No longer expected to fail anywhere."""
from sqlalchemy import text

def _has_timescaledb():
    from database.session_factory import SessionFactory
    try:
        with SessionFactory.get_session() as session:
            session.execute(text("SELECT 1 FROM timescaledb_information.hypertables LIMIT 1"))
            return True
    except Exception:
        return False

def test_hypertables_exist():
    """Alembic upgrade head sonrası hypertable'lar oluşmuş mu?"""
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        result = session.execute(text(
            "SELECT hypertable_name FROM timescaledb_information.hypertables "
            "WHERE hypertable_name IN ('decisions', 'weight_approvals')"
        ))
        names = {row[0] for row in result}
        assert "decisions" in names, "decisions hypertable eksik"
        assert "weight_approvals" in names, "weight_approvals hypertable eksik"
        # Faz 233: experiment_registry kasıtlı olarak kaldırıldı — kullanıcı
        # bulgusu: hiçbir ajan/karar mekanizması okumuyordu, sadece her
        # kararda (WAIT dahil) 1 satır yazan gereksiz bir denetim kaydıydı,
        # gerçek depolama büyümesine sebep oluyordu.
