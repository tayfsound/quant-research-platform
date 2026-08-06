"""Faz 230: kullanıcı isteği — sosyal medya sentiment. Reddit'in kimliksiz
API'si 403 verdiği için (doğrulandı), gerçek veri ücretsiz bir OAuth2
"script" uygulaması kaydı (REDDIT_CLIENT_ID/SECRET) gerektiriyor. Bu ortamda
kayıt yapılmadığı için test, gerçek ağ üzerinden dürüstçe "None" (fail-closed)
döndüğünü doğruluyor — sahte bir skor uydurulmadığını kanıtlıyor."""
import market_data.sentiment.reddit_provider as reddit_provider
from market_data.sentiment.reddit_provider import fetch_social_sentiment


def test_returns_none_without_reddit_credentials(monkeypatch):
    reddit_provider._CACHE = None
    monkeypatch.setenv("REDDIT_CLIENT_ID", "")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "")
    from config import get_settings
    get_settings.cache_clear()
    try:
        assert fetch_social_sentiment() is None
    finally:
        get_settings.cache_clear()
        reddit_provider._CACHE = None


def test_invalid_credentials_fail_closed_not_fake(monkeypatch):
    """Gerçek ağ üzerinden: uydurma bir client_id/secret ile Reddit'in
    kendi OAuth sunucusu 401/403 döner — sağlayıcı bunu yutup None
    döndürmeli, asla sahte bir skor üretmemeli."""
    reddit_provider._CACHE = None
    monkeypatch.setenv("REDDIT_CLIENT_ID", "invalid_test_client_id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "invalid_test_secret")
    from config import get_settings
    get_settings.cache_clear()
    try:
        assert fetch_social_sentiment() is None
    finally:
        get_settings.cache_clear()
        reddit_provider._CACHE = None
