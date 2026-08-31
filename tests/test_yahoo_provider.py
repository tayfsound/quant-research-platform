"""Faz 194: YahooProvider — kripto-olmayan varlıklar (endeks/emtia/hisse)
için gerçek OHLCV kaynağı. Gerçek ağa karşı test ediyor (Binance testlerinde
zaten kurulmuş konvansiyonla tutarlı — tests/test_market_data_provider.py:
test_binance_provider_works_from_inside_a_running_event_loop)."""
from market_data.ingestion.ohlcv import OHLCV
from market_data.ingestion.yahoo_provider import YahooProvider


def test_yahoo_provider_fetches_real_daily_bars_for_a_real_stock():
    data = YahooProvider().get_ohlcv("AAPL", "1d", limit=5)
    assert len(data) <= 5
    assert len(data) > 0
    assert isinstance(data[0], OHLCV)
    assert data[-1].close > 0


def test_yahoo_provider_fetches_real_index_data():
    data = YahooProvider().get_ohlcv("^GSPC", "1d", limit=3)
    assert len(data) > 0
    assert data[-1].close > 100  # S&P 500 seviyesi, gerçekçi bir alt sınır


def test_yahoo_provider_returns_empty_list_for_a_nonexistent_ticker():
    data = YahooProvider().get_ohlcv("THISISNOTAREALTICKERXYZ123", "1d", limit=5)
    assert data == []


def test_yahoo_provider_resamples_1h_bars_into_real_4h_bars():
    """Faz 214: yfinance'te gerçek bir "4h" interval yok — önceden istekte
    bulunulduğunda sessizce "1d"ye düşülüyordu. Artık 1h barlardan gerçek
    OHLCV kurallarıyla (open=ilk, high=max, low=min, close=son,
    volume=toplam) yeniden örnekleniyor."""
    hourly = YahooProvider().get_ohlcv("AAPL", "1h", limit=20)
    fourh = YahooProvider().get_ohlcv("AAPL", "4h", limit=5)

    assert len(fourh) > 0
    for bar in fourh:
        assert bar.high >= bar.low
        assert bar.high >= bar.open
        assert bar.high >= bar.close
        assert bar.volume > 0
    # 4h barların hacmi, tek bir 1h barın hacminden belirgin şekilde
    # büyük olmalı (4 barın toplamı) — gerçekten agregatlandığının kanıtı.
    assert fourh[-1].volume > hourly[-1].volume


def test_yahoo_provider_enforces_a_hard_timeout_when_the_call_hangs(monkeypatch):
    """Faz 393 — gerçek olay: `symbol_propose_timing` loglarında AMDUSDT
    ile INTCUSDT arasında 819sn'lik açıklanamayan bir boşluk bulundu,
    worker o pencerede tamamen donmuştu. Kök neden: yfinance'in kendi
    `timeout=10`'u SADECE OHLCV isteğine uygulanıyor, çerez/crumb alma
    adımına değil — o adım askıda kalabiliyor. Bu test, TÜM çağrının
    (crumb dahil) uygulama seviyesinde sert bir üst sınırla sarmalandığını
    doğruluyor: `yf.Ticker` sonsuza kadar asılı kalan sahte bir modülle
    değiştiriliyor (`sys.modules["yfinance"]`), `_HARD_TIMEOUT_SECONDS`
    hızlı test için küçültülüyor."""
    import sys
    import time

    import market_data.ingestion.yahoo_provider as yahoo_provider_module

    monkeypatch.setattr(yahoo_provider_module, "_HARD_TIMEOUT_SECONDS", 0.2)

    class _HangingTicker:
        def __init__(self, symbol):
            pass

        def history(self, period, interval):
            time.sleep(5)  # _HARD_TIMEOUT_SECONDS'tan (0.2) çok daha uzun.
            raise AssertionError("bu satıra hiç ulaşılmamalı, timeout önce tetiklenmeli")

    fake_yfinance = type(sys)("yfinance")
    fake_yfinance.Ticker = _HangingTicker
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)

    start = time.monotonic()
    data = yahoo_provider_module.YahooProvider().get_ohlcv("HANGTEST", "1d", limit=5)
    elapsed = time.monotonic() - start

    assert data == []
    assert elapsed < 2.0  # gerçek donma (5sn) değil, timeout'un (0.2sn) hemen sonrası
