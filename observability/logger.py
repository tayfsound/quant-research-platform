"""Structlog tabanlı yapılandırılmış loglama — version bilgisiyle."""
import structlog

from config import get_settings
from version import PROMPT_VERSION, SYSTEM_VERSION


def setup_logging() -> None:
    settings = get_settings()
    structlog.configure(
        processors=[
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
        logger_factory=structlog.PrintLoggerFactory(),
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
