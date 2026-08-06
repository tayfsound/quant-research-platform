"""Gap #18: /stream/live used to broadcast random.choice/random.uniform
fake data — LivePredictions.tsx displayed it as if it were a real model
output. Also, the route is registered under prefix="/api/v1" in api/main.py
but the frontend was connecting to a bare `ws://.../stream/live` (no
`/api/v1`), which would 404 in a real browser — never actually verified
end to end.

Faz 215: kullanıcı bulgusu — "sadece BTC var, watchlist'teki bütün
tokenları otomatik eklemiyor." Bu artık her tick'te tek bir sembol için
CognitiveOrchestrator.run_cycle() çalıştırmıyor — api/rest/tokens.py::
build_tokens_list() ile AYNI, zaten hesaplanmış gerçek veriyi (decisions
tablosundaki en son karar, watchlist'teki HER sembol için) okuyor."""


def test_stream_live_broadcasts_every_watchlist_symbol_not_just_one():
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    with client.websocket_connect("/api/v1/stream/live") as ws:
        data = ws.receive_json()

    tokens = data["tokens"]
    assert len(tokens) > 1  # sadece BTC değil, watchlist'in tamamı

    symbols = {t["symbol"] for t in tokens}
    assert "BTCUSDT" in symbols

    for t in tokens:
        assert "direction" in t
        assert "confidence" in t
        assert "is_crypto" in t
        assert "market_open" in t
