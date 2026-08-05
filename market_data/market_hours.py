"""Faz 195: piyasa saati farkındalığı — gerçek bulgu, kripto çevresi 24/7
olduğu için sistem hisse/endeks için de aynı varsayımla çalışıyordu; NYSE/
NASDAQ kapalıyken (gece, hafta sonu) AAPL/^GSPC gibi sembolleri son (eski)
kapanış fiyatıyla analiz edip gerçekmiş gibi işlem denemeye çalışıyordu.

Kapsam bilinçli olarak sınırlı: ABD resmi tatilleri hesaba katılmıyor
(NYSE takvimi ayrı bir veri kaynağı gerektirir) — sadece hafta içi/hafta
sonu + gerçek saat aralığı kontrol ediliyor. Bu, "gece yarısı işlem
denemesin" sorununun büyük kısmını çözüyor; birkaç tatil günü kaçırılmış
bir "kapalı" tespiti yapabilir, bu düşük riskli ve dokümante bir sınır."""
from datetime import datetime
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

_CRYPTO_SUFFIXES = ("USDT", "BUSD", "USDC", "FDUSD")

# Hisse/endeks — NYSE/NASDAQ düzenli seans: 09:30-16:00 ET, Pazartesi-Cuma.
_EQUITY_SYMBOLS = {"AAPL", "NVDA", "MSFT", "^IXIC", "^GSPC"}

# Emtia vadeli işlemleri (CME) — neredeyse 23/5: Pazar 18:00 ET'den
# Cuma 17:00 ET'ye kadar, günlük 17:00-18:00 ET arası kısa bir mola ile.
_FUTURES_SYMBOLS = {"GC=F", "SI=F"}


def is_market_open(symbol: str, now: datetime | None = None) -> bool:
    """Kripto için her zaman True (gerçekten 7/24 işlem görüyor). Hisse/
    endeks/emtia için gerçek ET saatine göre hesaplanıyor."""
    symbol = symbol.upper()
    if symbol.endswith(_CRYPTO_SUFFIXES):
        return True

    now_et = (now or datetime.now(_ET)).astimezone(_ET)
    weekday = now_et.weekday()  # 0=Pazartesi ... 6=Pazar
    minutes = now_et.hour * 60 + now_et.minute

    if symbol in _EQUITY_SYMBOLS:
        if weekday >= 5:
            return False
        return 9 * 60 + 30 <= minutes < 16 * 60

    if symbol in _FUTURES_SYMBOLS:
        if weekday == 5:  # Cumartesi tamamen kapalı
            return False
        if weekday == 6:  # Pazar, sadece 18:00'dan sonra açık
            return minutes >= 18 * 60
        if weekday == 4:  # Cuma, 17:00'da kapanıyor
            return minutes < 17 * 60
        # Salı-Perşembe: günlük 17:00-18:00 arası kısa mola dışında açık.
        return not (17 * 60 <= minutes < 18 * 60)

    # Tanımadığımız bir sembol — güvenli varsayım: her zaman açık say
    # (mevcut davranışla aynı, bilinen semboller için gerçek kısıt ekliyoruz).
    return True
