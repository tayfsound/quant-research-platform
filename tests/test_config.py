"""Config modülü için temel test."""
from config import get_settings


def test_settings_defaults() -> None:
    s = get_settings()
    assert s.API_PORT == 8000
    assert s.APP_ENV == "development"
    assert s.LOG_LEVEL == "DEBUG"
