"""Faz 224: kullanıcı bulgusu — "PNL de para birimi görünmüyor bu hangi
birimle kayıp belli değil dolar mı btc mi vs... her yerde aynı problem
var." Gerçek, canlı dönüşüm oranları — Binance'in kendi piyasalarından
(BTCUSDT, USDTTRY), ayrı bir FX API'sine gerek yok."""
from market_data.fx.currency_provider import fetch_currency_rates


def test_fetch_currency_rates_returns_real_positive_rates():
    rates = fetch_currency_rates()
    assert rates["usd_btc"] is not None and rates["usd_btc"] > 0
    assert rates["usd_try"] is not None and rates["usd_try"] > 0
    # 1 USD çok daha az bir BTC eder (BTC > 1 USD) — makul aralık kontrolü.
    assert rates["usd_btc"] < 0.01
    # 1 USD -> TRY, makul bir aralıkta (gerçek kur, aşırı uçta değil).
    assert 1 < rates["usd_try"] < 1000
