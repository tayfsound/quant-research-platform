"""Structlog tabanlı yapılandırılmış loglama — version bilgisiyle."""
import logging

import structlog

from config import get_settings
from version import PROMPT_VERSION, SYSTEM_VERSION


def setup_logging() -> None:
    settings = get_settings()
    # Faz 269-sonrası — gerçek bulgu: setup_logging() hiçbir yerden
    # çağrılmadığı için bu satır hiç fark edilmemiş bir uyumsuzluk
    # taşıyordu — structlog.stdlib.filter_by_level/add_logger_name,
    # Python'un GERÇEK logging.Logger nesnesini (getEffectiveLevel()/
    # .name/.disabled) bekler, ama logger_factory PrintLoggerFactory()
    # idi (düz stdout yazıcısı, bu attribute'lara sahip değil) —
    # çağrıldığı anda AttributeError ile patlardı (doğrulandı, bu
    # oturumda setup_logging() ilk kez gerçekten çağrılınca ortaya
    # çıktı). stdlib.LoggerFactory() doğru eşleşme — artık Python'un
    # GERÇEK logging modülü üzerinden akıyor, handler'lar/seviye
    # kontrolü standart yollarla çalışır.
    logging.basicConfig(level=logging.INFO)
    structlog.configure(
        processors=[
            # Faz 269-sonrası — distributed tracing: services/orchestrator.py
            # ve services/celery_app.py'nin contextvars ile bind ettiği
            # cycle_id/celery_task_id gibi alanları HER log satırına otomatik
            # ekler. Bu, structlog'un kendi varsayılan zincirinde zaten var
            # (26.1.0) ama setup_logging() ÖZEL bir processors listesi
            # verdiği için o varsayılanı tamamen EZİYOR — burada AÇIKÇA
            # eklenmezse hiç çalışmaz (örtük kütüphane varsayımına güvenmek
            # yerine).
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
            if settings.APP_ENV != "development"
            else structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

def get_logger(name: str | None = None, **kwargs) -> structlog.stdlib.BoundLogger:
    logger = structlog.get_logger(name or __name__)
    # Otomatik version bağlama
    logger = logger.bind(
        system_version=SYSTEM_VERSION,
        prompt_version=PROMPT_VERSION,
    )
    if kwargs:
        logger = logger.bind(**kwargs)
    return logger  # type: ignore[return-value]
