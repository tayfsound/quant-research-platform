"""Backlog #49 (Faz 365) — Binance forceOrder mesaj ayrıştırma."""
from datetime import UTC, datetime

from services.binance_liquidation_listener import _parse_force_order


def _raw(symbol="BTCUSDT", side="SELL", qty="0.014", price="9910", ap=None, t=1568014460893):
    order = {"s": symbol, "S": side, "q": qty, "p": price, "T": t}
    if ap is not None:
        order["ap"] = ap
    return {"e": "forceOrder", "E": t, "o": order}


def test_sell_side_maps_to_long_liquidated():
    event = _parse_force_order(_raw(side="SELL"))
    assert event["liquidated_side"] == "LONG"


def test_buy_side_maps_to_short_liquidated():
    event = _parse_force_order(_raw(side="BUY"))
    assert event["liquidated_side"] == "SHORT"


def test_prefers_average_price_over_raw_price():
    event = _parse_force_order(_raw(price="9910", ap="9905"))
    assert event["price"] == 9905.0


def test_falls_back_to_raw_price_when_no_average():
    event = _parse_force_order(_raw(price="9910"))
    assert event["price"] == 9910.0


def test_computes_notional_from_price_times_quantity():
    event = _parse_force_order(_raw(qty="2.0", price="100"))
    assert event["notional_usd"] == 200.0


def test_converts_epoch_ms_to_utc_datetime():
    event = _parse_force_order(_raw(t=1568014460893))
    assert event["time"] == datetime.fromtimestamp(1568014460893 / 1000, tz=UTC)


def test_missing_order_payload_returns_none():
    assert _parse_force_order({"e": "forceOrder"}) is None


def test_missing_required_field_returns_none():
    raw = _raw()
    del raw["o"]["q"]
    assert _parse_force_order(raw) is None


def test_unexpected_side_value_returns_none():
    assert _parse_force_order(_raw(side="HOLD")) is None
