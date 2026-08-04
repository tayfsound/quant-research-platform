"""Veritabanı bağlantısı.

Faz 182: DATABASE_URL was hardcoded to localhost:5432 here, completely
ignoring config/settings.py's DATABASE_URL_SYNC (which reads DATABASE_URL_SYNC
from the environment/.env). This is the actual `engine` object used
throughout the app (SessionFactory, every repository) — so no environment
variable, K8s Secret, or .env override ever had any effect on where the app
actually connects. Found because a real K8s deployment of the api pod
crash-looped trying to reach localhost instead of the `postgres` Service.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import get_settings

settings = get_settings()

engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def get_session():
    return SessionLocal()
