"""SessionFactory — her işlem için yeni session, uzun ömürlü bağlantı yok."""
from contextlib import contextmanager

from database.connection import SessionLocal


class SessionFactory:
    @staticmethod
    @contextmanager
    def get_session():
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
